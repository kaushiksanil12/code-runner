import json
import time
import subprocess
import os
import tempfile
import shutil
import sqlite3
import boto3

# --- Language Definitions ---
LANGUAGES = {
    "python": {"filename": "main.py", "cmd": ["python3", "{work_dir}/main.py"]},
    "javascript": {"filename": "main.js", "cmd": ["node", "{work_dir}/main.js"]},
    "java": {"filename": "Main.java", "cmd": ["sh", "-c", "javac -d {work_dir} {work_dir}/Main.java && java -cp {work_dir} Main"]},
    "c": {"filename": "main.c", "cmd": ["sh", "-c", "gcc {work_dir}/main.c -o {work_dir}/out && {work_dir}/out"]},
    "cpp": {"filename": "main.cpp", "cmd": ["sh", "-c", "g++ {work_dir}/main.cpp -o {work_dir}/out && {work_dir}/out"]},
    "csharp": {"filename": "Program.cs", "cmd": ["sh", "-c", "cp -r /var/task/csharp_template {work_dir}/app && cp -r /var/task/dotnet_home {work_dir}/dotnet_home && export HOME={work_dir}/dotnet_home && export DOTNET_CLI_HOME={work_dir}/dotnet_home && cp {work_dir}/Program.cs {work_dir}/app/Program.cs && cd {work_dir}/app && dotnet run --no-restore -p:WarningLevel=0"]},
}

# --- Aliases ---
ALIASES = {
    "python": "python", "py": "python", "python3": "python", "python2": "python",
    "javascript": "javascript", "js": "javascript", "node": "javascript", "nodejs": "javascript",
    "java": "java", "c": "c", "c++": "cpp", "cpp": "cpp", "cc": "cpp", "cxx": "cpp",
    "c#": "csharp", "cs": "csharp", "csharp": "csharp", "dotnet": "csharp", ".net": "csharp"
}

DISPLAY_NAMES = {
    "python": "Python", "javascript": "JavaScript", "java": "Java",
    "c": "C", "cpp": "C++", "csharp": "C#"
}


def resolve_language(raw: str):
    if not isinstance(raw, str) or not raw.strip():
        supported = ", ".join(sorted(DISPLAY_NAMES.values()))
        return None, f"Missing or empty 'language' field. Supported: {supported}"
    normalized = raw.strip().lower()
    canonical = ALIASES.get(normalized)
    if not canonical:
        supported = ", ".join(sorted(DISPLAY_NAMES.values()))
        return None, f"Unsupported language: '{raw}'. Supported languages: {supported}."
    return canonical, None


def lambda_handler(event, context):
    """AWS Lambda handler for executing untrusted code securely."""

    # =========================================================================
    # PATH 1: SQL EVALUATION (LMS evaluate_sql sends s3_key and user_query)
    # =========================================================================
    s3_key = event.get("s3_key")
    user_query = event.get("user_query")

    if s3_key and user_query:
        s3_client = boto3.client('s3')
        s3_bucket = os.environ.get('S3_DB_BUCKET', 's3-code-runner')

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name

        try:
            # Download the fresh database built by db_builder.py
            s3_client.download_file(s3_bucket, s3_key, db_path)

            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Execute the student's query
            cursor.execute(user_query)

            # Format results into a JSON Array of Dicts exactly as the LMS expects
            columns = [d[0] for d in cursor.description] if cursor.description else []
            rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

            conn.close()

            return {
                "status": "success",
                "result": rows
            }

        except sqlite3.Error as e:
            return {"status": "error", "error_type": "sql_error", "message": str(e)}
        except Exception as e:
            return {"status": "error", "error_type": "infra_error", "message": str(e)}
        finally:
            if os.path.exists(db_path):
                os.remove(db_path)

    # =========================================================================
    # PATH 2: STANDARD CODE RUNNER (Python, JS, Java, etc.)
    # =========================================================================
    raw_language = event.get("language", "")
    source_code  = event.get("source_code", "")
    stdin        = event.get("stdin", "")

    if not isinstance(stdin, str):
        stdin = str(stdin) if stdin is not None else ""

    language, err = resolve_language(raw_language)
    if err:
        return {"status": "Error", "stdout": "", "stderr": err, "exit_code": -1, "time_ms": 0}

    if not source_code.strip():
        return {"status": "Error", "stdout": "", "stderr": "source_code is empty.", "exit_code": -1, "time_ms": 0}

    lang_config = LANGUAGES[language]
    start = time.time()
    work_dir = tempfile.mkdtemp(prefix="exec_")

    try:
        file_path = os.path.join(work_dir, lang_config["filename"])
        with open(file_path, "w") as f:
            f.write(source_code)

        raw_cmd = lang_config["cmd"]
        cmd = [c.replace("{work_dir}", work_dir) for c in raw_cmd]

        proc = subprocess.run(
            cmd,
            input=stdin,
            capture_output=True,
            text=True,
            timeout=29.5
        )

        stdout = proc.stdout[:1_000_000]
        stderr = proc.stderr[:100_000]

        if language == "csharp":
            stdout = stdout.replace(
                "An issue was encountered verifying workloads. "
                "For more information, run \"dotnet workload update\".\n", ""
            )

        return {
            "status":    "OK" if proc.returncode == 0 else "Error",
            "stdout":    stdout,
            "stderr":    stderr,
            "exit_code": proc.returncode,
            "time_ms":   int((time.time() - start) * 1000),
            "memory_mb": getattr(context, "memory_limit_in_mb", "unknown"),
            "language":  DISPLAY_NAMES[language],
        }

    except subprocess.TimeoutExpired as e:
        return {
            "status":    "Error",
            "stdout":    (e.stdout or "")[:1_000_000],
            "stderr":    (e.stderr or "")[:100_000] + "\nExecution timed out after 29.5 seconds.",
            "exit_code": 124,
            "time_ms":   int((time.time() - start) * 1000),
            "memory_mb": getattr(context, "memory_limit_in_mb", "unknown"),
            "language":  DISPLAY_NAMES[language],
        }
    except Exception as e:
        return {
            "status":    "Error",
            "stdout":    "",
            "stderr":    f"Internal Lambda execution error: {str(e)}",
            "exit_code": -1,
            "time_ms":   int((time.time() - start) * 1000),
            "language":  DISPLAY_NAMES.get(language, raw_language),
        }
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)