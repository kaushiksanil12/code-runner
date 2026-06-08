FROM python:3.12-slim-bookworm

WORKDIR /app

# Only the API server dependencies are needed now
COPY requirements.txt .
# Ensure boto3 is installed for AWS Lambda invocation
RUN pip install --no-cache-dir -r requirements.txt boto3

COPY code/ /app/

# Run as an unprivileged user (nobody) since no isolation privileges are needed
RUN useradd -u 10000 -m app_user
RUN chown -R app_user:app_user /app
USER 10000:10000

CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port 8000 --workers ${WORKERS:-1}"]