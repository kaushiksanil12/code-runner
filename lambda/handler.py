import json
import time
import subprocess
import os
import tempfile
import shutil

# --- Language Definitions ---
LANGUAGES = {
    "python": {
        "filename": "main.py",
        "cmd": ["python3", "{work_dir}/main.py"]
    },
    "javascript": {
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
        "cmd": ["sh", "-c", "cp -r /var/task/csharp_template {work_dir}/app && cp -r /var/task/dotnet_home {work_dir}/dotnet_home && export HOME={work_dir}/dotnet_home && export DOTNET_CLI_HOME={work_dir}/dotnet_home && cp {work_dir}/Program.cs {work_dir}/app/Program.cs && cd {work_dir}/app && dotnet run --no-restore -p:WarningLevel=0"]
    },
    "sql": {
        "filename": "main.sql",
        "cmd": ["sh", "-c", "sqlite3 {work_dir}/db.sqlite < {work_dir}/main.sql"]
    }
}

# --- Aliases: all lowercased → canonical key in LANGUAGES ---
ALIASES = {
    # Python
    "python":    "python",
    "py":         "python",
    "python3":    "python",
    "python2":    "python",
    # JavaScript
    "js":         "javascript",
    "node":       "javascript",
    "nodejs":     "javascript",
    # Java
    "java":       "java",
    # C
    "c":          "c",
    # C++
    "c++":        "cpp",
    "cpp":        "cpp",
    "cc":         "cpp",
    "cxx":        "cpp",
    # C#
    "c#":         "csharp",
    "cs":         "csharp",
    "csharp":     "csharp",
    "dotnet":     "csharp",
    ".net":       "csharp",
    # SQL
    "sql":        "sql",
    "sqlite":     "sql",
    "sqlite3":    "sql",
}

# Human-readable names for error messages
DISPLAY_NAMES = {
    "python":     "Python",
    "javascript": "JavaScript",
    "java":       "Java",
    "c":          "C",
    "cpp":        "C++",
    "csharp":     "C#",
    "sql":        "SQL",
}

def resolve_language(raw: str):
    """Normalize any user-supplied language string to a canonical LANGUAGES key.
    Returns (canonical_key, None) on success or (None, error_message) on failure.
    """
    if not isinstance(raw, str) or not raw.strip():
        supported = ", ".join(sorted(DISPLAY_NAMES.values()))
        return None, f"Missing or empty 'language' field. Supported: {supported}"

    normalized = raw.strip().lower()
    canonical = ALIASES.get(normalized)

    if not canonical:
        supported = ", ".join(sorted(DISPLAY_NAMES.values()))
        return None, (
            f"Unsupported language: '{raw}'. "
            f"Supported languages and aliases: {supported}. "
            f"Common aliases: py, js, cpp, c#, cs, sql."
        )

    return canonical, None


def lambda_handler(event, context):
    """AWS Lambda handler for executing untrusted code securely.
    Expects event payload: {"language": "...", "source_code": "...", "stdin": "..."}
    """
    raw_language = event.get("language", "")
    source_code  = event.get("source_code", "")
    stdin        = event.get("stdin", "")

    # Coerce stdin to string safely (caller might pass int/None)
    if not isinstance(stdin, str):
        stdin = str(stdin) if stdin is not None else ""

    # Resolve language
    language, err = resolve_language(raw_language)
    if err:
        return {
            "status":   "Error",
            "stdout":   "",
            "stderr":   err,
            "exit_code": -1,
            "time_ms":  0
        }

    # Guard: empty source code
    if not source_code.strip():
        return {
            "status":   "Error",
            "stdout":   "",
            "stderr":   "source_code is empty.",
            "exit_code": -1,
            "time_ms":  0
        }

    lang_config = LANGUAGES[language]
    start = time.time()

    work_dir = tempfile.mkdtemp(prefix="exec_")

    try:
        file_path = os.path.join(work_dir, lang_config["filename"])
        with open(file_path, "w") as f:
            f.write(source_code)

        raw_cmd = lang_config["cmd"]
        cmd = [c.replace("{work_dir}", work_dir) for c in raw_cmd]

        s3_bucket = event.get("s3_db_bucket")
        user_id = event.get("user_id", "default_user")
        s3_key = f"db_{user_id}.sqlite"
        db_file = os.path.join(work_dir, "db.sqlite")
        
        if language == "sql" and s3_bucket:
            import boto3
            import botocore
            from datetime import datetime, timezone
            s3 = boto3.client("s3")
            try:
                # Check file age to enforce 1-hour expiration
                obj = s3.head_object(Bucket=s3_bucket, Key=s3_key)
                last_modified = obj['LastModified']
                
                # If older than 1 hour (3600 seconds), do not download (starts fresh)
                if (datetime.now(timezone.utc) - last_modified).total_seconds() <= 3600:
                    s3.download_file(s3_bucket, s3_key, db_file)
            except botocore.exceptions.ClientError as e:
                if e.response['Error']['Code'] in ("404", "NoSuchKey"):
                    pass
                else:
                    raise

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

        if language == "sql" and s3_bucket:
            if os.path.exists(db_file):
                s3.upload_file(db_file, s3_bucket, s3_key)

        return {
            "status":    "OK" if proc.returncode == 0 else "Error",
            "stdout":    stdout,
            "stderr":    stderr,
            "exit_code": proc.returncode,
            "time_ms":   int((time.time() - start) * 1000),
            "memory_mb": getattr(context, "memory_limit_in_mb", "unknown"),
            "language":  DISPLAY_NAMES[language],   # echo back the resolved name
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