import time
import subprocess
import os
import tempfile
import shutil
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="Secure Code Execution Engine")

SUPPORTED_LANGUAGES = {
    "python",
    "node",
    "c",
    "cpp",
    "java",
    "csharp",
    "sql",
}

class ExecutionRequest(BaseModel):
    language: str
    source_code: str = Field(..., max_length=65536)
    stdin: str = Field(default="", max_length=65536)

def set_resource_limits():
    """Sets CPU, Memory, and Process limits for the execution subprocess."""
    import resource
    # Prevent fork bombs: max 1000 processes/threads (shared with Uvicorn and .NET workers)
    resource.setrlimit(resource.RLIMIT_NPROC, (1000, 1000))
    # Note: RLIMIT_AS (Virtual Memory) is intentionally not set.
    # Modern runtimes like .NET and JVM reserve gigabytes of virtual memory space (PROT_NONE).
    # Actual memory usage is safely bounded by Docker's mem_limit: 1g.
    # Limit CPU time to 5 seconds
    resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
    # Limit file size creation to 50MB (.NET binaries easily exceed 10MB)
    # Note: RLIMIT_FSIZE is removed because .NET MSBuild generates massive intermediate build files.

def run_sandboxed(command: list, work_dir: str, timeout_secs: int = 5, stdin_data: str = ""):
    """
    Executes a command inside a strict bubblewrap sandbox.
    """
    bwrap_cmd = [
        "bwrap",
        "--ro-bind", "/", "/",               # Read-only root filesystem
        "--dev", "/dev",                     # Provide /dev
        "--proc", "/proc",                   # Provide /proc
        "--tmpfs", "/tmp",                   # Empty, temporary /tmp
        "--bind", work_dir, work_dir,        # Allow write access only to the workspace
        "--unshare-all",                     # Isolate network, pid, ipc, user namespaces
        "--die-with-parent",                 # Kill sandbox if parent dies
        "--chdir", work_dir,                 # Start inside the workspace
        "--uid", "1000",                     # Run as the unprivileged web server UID
        "--gid", "1000",                     # Run as the unprivileged web server GID
    ] + command

    try:
        # Pass a clean, minimal environment
        env = {
            "PATH": "/usr/local/bin:/usr/bin:/bin:/usr/share/dotnet",
            "HOME": work_dir,
            "DOTNET_ROOT": "/usr/share/dotnet",
            "DOTNET_CLI_HOME": work_dir,
            "DOTNET_CLI_TELEMETRY_OPTOUT": "1",
            "DOTNET_SKIP_FIRST_TIME_EXPERIENCE": "1",
            "DOTNET_NOLOGO": "1",
            "DOTNET_CLI_WORKLOAD_UPDATE_NOTIFY": "0"
        }
        
        proc = subprocess.run(
            bwrap_cmd,
            env=env,
            input=stdin_data,
            capture_output=True,
            text=True,
            timeout=timeout_secs,
            preexec_fn=set_resource_limits
        )
        return {"stdout": proc.stdout, "stderr": proc.stderr, "exit_code": proc.returncode}
    except subprocess.TimeoutExpired as e:
        return {
            "stdout": e.stdout or "",
            "stderr": (e.stderr or "") + f"\nExecution timed out after {timeout_secs} seconds.",
            "exit_code": 124
        }
    except Exception as e:
        return {"stdout": "", "stderr": "Internal execution error occurred.", "exit_code": -1}

@app.post("/execute")
def execute_code(request: ExecutionRequest):
    start = time.time()

    if request.language not in SUPPORTED_LANGUAGES:
        raise HTTPException(status_code=400, detail=f"Unsupported language: {request.language}")

    # Create isolated workspace on the host (/tmp is mounted as a tmpfs in docker-compose)
    work_dir = tempfile.mkdtemp(prefix="exec_")
    
    result = {"stdout": "", "stderr": "", "exit_code": 0}

    try:
        if request.language == "python":
            file_path = os.path.join(work_dir, "script.py")
            with open(file_path, "w") as f:
                f.write(request.source_code)
            result = run_sandboxed(["python3", "script.py"], work_dir, stdin_data=request.stdin)

        elif request.language == "node":
            file_path = os.path.join(work_dir, "script.js")
            with open(file_path, "w") as f:
                f.write(request.source_code)
            result = run_sandboxed(["node", "script.js"], work_dir, stdin_data=request.stdin)

        elif request.language == "c":
            file_path = os.path.join(work_dir, "main.c")
            with open(file_path, "w") as f:
                f.write(request.source_code)
            
            compile_res = run_sandboxed(["gcc", "main.c", "-o", "main"], work_dir)
            if compile_res["exit_code"] != 0:
                result = compile_res
            else:
                result = run_sandboxed(["./main"], work_dir, stdin_data=request.stdin)

        elif request.language == "cpp":
            file_path = os.path.join(work_dir, "main.cpp")
            with open(file_path, "w") as f:
                f.write(request.source_code)
            
            compile_res = run_sandboxed(["g++", "main.cpp", "-o", "main"], work_dir)
            if compile_res["exit_code"] != 0:
                result = compile_res
            else:
                result = run_sandboxed(["./main"], work_dir, stdin_data=request.stdin)

        elif request.language == "java":
            file_path = os.path.join(work_dir, "Main.java")
            with open(file_path, "w") as f:
                f.write(request.source_code)
            
            compile_res = run_sandboxed(["javac", "-J-Xmx256m", "Main.java"], work_dir)
            if compile_res["exit_code"] != 0:
                result = compile_res
            else:
                result = run_sandboxed(["java", "-Xmx256m", "-XX:CompressedClassSpaceSize=64m", "-Xms64m", "Main"], work_dir, stdin_data=request.stdin)

        elif request.language == "csharp":
            app_dir = os.path.join(work_dir, "App")
            if os.path.exists("/app/csharp_template"):
                shutil.copytree("/app/csharp_template", app_dir)
            else:
                os.mkdir(app_dir)
                subprocess.run(["dotnet", "new", "console", "-o", app_dir, "--force"])
            
            file_path = os.path.join(app_dir, "Program.cs")
            with open(file_path, "w") as f:
                f.write(request.source_code)
            
            result = run_sandboxed(["dotnet", "run", "--no-restore", "--project", "App"], work_dir, stdin_data=request.stdin)

        elif request.language == "sql":
            file_path = os.path.join(work_dir, "query.sql")
            with open(file_path, "w") as f:
                f.write(request.source_code)
            
            with open(file_path, "r") as f:
                sql_content = f.read()
            
            result = run_sandboxed(["sqlite3", ":memory:"], work_dir, stdin_data=sql_content)

    except Exception as e:
        result = {"stdout": "", "stderr": "Internal server error during processing.", "exit_code": -1}
    finally:
        # Wipe the workspace on the host side
        shutil.rmtree(work_dir, ignore_errors=True)

    elapsed = int((time.time() - start) * 1000)

    stdout = result.get("stdout", "")
    if request.language == "csharp":
        stdout = stdout.replace("An issue was encountered verifying workloads. For more information, run \"dotnet workload update\".\n", "")

    return {
        "status": "OK" if result.get("exit_code") == 0 else "Error",
        "stdout": stdout,
        "stderr": result.get("stderr", ""),
        "exit_code": result.get("exit_code", 0),
        "time_ms": elapsed,
    }
