import json
import time
import subprocess
import os
import tempfile
import shutil

# --- Language Definitions ---
# The Lambda task root is read-only, so all compilations/executions must output to /tmp.
LANGUAGES = {
    "python": {
        "filename": "main.py",
        "cmd": ["python3", "{work_dir}/main.py"]
    },
    "node": {
        "filename": "main.js",
        "cmd": ["node", "{work_dir}/main.js"]
    },
    "java": {
        "filename": "Main.java",
        "cmd": ["sh", "-c", "javac -d {work_dir} {work_dir}/Main.java && java -cp {work_dir} Main"]
    },
    "c": {
        "filename": "main.c",
        "cmd": ["sh", "-c", "gcc {work_dir}/main.c -o {work_dir}/out && {work_dir}/out"]
    },
    "cpp": {
        "filename": "main.cpp",
        "cmd": ["sh", "-c", "g++ {work_dir}/main.cpp -o {work_dir}/out && {work_dir}/out"]
    },
    "csharp": {
        "filename": "Program.cs",
        # Copy the pre-built template from the task root to /tmp to make it writable
        "cmd": ["sh", "-c", "cp -r /var/task/csharp_template {work_dir}/app && cp {work_dir}/Program.cs {work_dir}/app/Program.cs && cd {work_dir}/app && dotnet run --no-restore"]
    },
    "sql": {
        "filename": "main.sql",
        "cmd": ["sh", "-c", "sqlite3 {work_dir}/db.sqlite < {work_dir}/main.sql"]
    }
}

def lambda_handler(event, context):
    """
    AWS Lambda handler for executing untrusted code securely.
    Expects event payload: {"language": "...", "source_code": "...", "stdin": "..."}
    """
    language = event.get("language")
    source_code = event.get("source_code", "")
    stdin = event.get("stdin", "")
    
    if language not in LANGUAGES:
        return {
            "status": "Error",
            "stdout": "",
            "stderr": f"Unsupported language: {language}",
            "exit_code": -1,
            "time_ms": 0
        }

    lang_config = LANGUAGES[language]
    start = time.time()
    
    # Create an isolated temporary directory in /tmp
    # AWS Lambda allows up to 10GB (default 512MB) in /tmp
    work_dir = tempfile.mkdtemp(prefix="exec_")
    
    try:
        # Write user source code
        file_path = os.path.join(work_dir, lang_config["filename"])
        with open(file_path, "w") as f:
            f.write(source_code)
            
        # Format the command with the dynamically generated temporary directory
        raw_cmd = lang_config["cmd"]
        cmd = [c.replace("{work_dir}", work_dir) for c in raw_cmd]

        # Enforce a 9.5 second timeout to ensure we return a structured JSON timeout response
        # before AWS violently terminates the Lambda container at exactly 10.0 seconds.
        proc = subprocess.run(
            cmd,
            input=stdin,
            capture_output=True,
            text=True,
            timeout=9.5
        )
        
        # Cap output size to prevent Lambda memory exhaustion or bloated payload limits
        stdout = proc.stdout[:1_000_000]
        stderr = proc.stderr[:100_000]
        
        # Strip noisy .NET SDK update messages
        if language == "csharp":
            stdout = stdout.replace("An issue was encountered verifying workloads. For more information, run \"dotnet workload update\".\n", "")
            
        return {
            "status": "OK" if proc.returncode == 0 else "Error",
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": proc.returncode,
            "time_ms": int((time.time() - start) * 1000)
        }
        
    except subprocess.TimeoutExpired as e:
        return {
            "status": "Error",
            "stdout": (e.stdout or "")[:1_000_000],
            "stderr": (e.stderr or "")[:100_000] + "\nExecution timed out after 9.5 seconds.",
            "exit_code": 124,
            "time_ms": int((time.time() - start) * 1000)
        }
    except Exception as e:
        return {
            "status": "Error",
            "stdout": "",
            "stderr": f"Internal Lambda execution error: {str(e)}",
            "exit_code": -1,
            "time_ms": int((time.time() - start) * 1000)
        }
    finally:
        # Cleanup /tmp to prevent space exhaustion across warm invocations
        shutil.rmtree(work_dir, ignore_errors=True)
