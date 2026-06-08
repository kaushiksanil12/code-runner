import time
import json
import os
import boto3
from botocore.exceptions import ClientError, BotoCoreError
from collections import defaultdict
from fastapi import FastAPI, HTTPException, Depends, Header, Request
from pydantic import BaseModel

app = FastAPI(title="Secure Code Execution Engine (AWS Lambda)")

# --- Rate Limiting & Auth ---
API_KEY = os.environ.get("API_KEY", "super-secure-key")
RATE_LIMIT_WINDOW = 60
MAX_REQUESTS = 15
request_counts = defaultdict(list)

# --- AWS Config ---
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
LAMBDA_FUNCTION_NAME = os.environ.get("LAMBDA_FUNCTION_NAME", "SecureCodeRunner")

# Initialize boto3 client. Assumes IAM Role is attached to the EC2 instance
# or AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY are provided in the environment.
try:
    lambda_client = boto3.client('lambda', region_name=AWS_REGION)
except Exception as e:
    print(f"Warning: Failed to initialize boto3 client: {e}")
    lambda_client = None

def check_rate_limit(request: Request):
    client_ip = request.client.host
    now = time.time()
    counts = request_counts[client_ip]
    counts = [t for t in counts if now - t < RATE_LIMIT_WINDOW]
    if len(counts) >= MAX_REQUESTS:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    counts.append(now)
    request_counts[client_ip] = counts

def verify_api_key(x_api_key: str = Header(...)):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API Key")

class ExecutionRequest(BaseModel):
    language: str
    source_code: str
    stdin: str = ""

@app.get("/health")
def health_check():
    return {"status": "healthy", "architecture": "aws_lambda"}

@app.post("/execute")
def execute_code(request: ExecutionRequest, _ = Depends(check_rate_limit), __ = Depends(verify_api_key)):
    start = time.time()
    
    if lambda_client is None:
         raise HTTPException(status_code=500, detail="AWS Lambda client not initialized. Check IAM permissions.")

    # Prepare the payload for Lambda
    payload = {
        "language": request.language,
        "source_code": request.source_code,
        "stdin": request.stdin
    }

    try:
        # Invoke the Lambda function synchronously
        response = lambda_client.invoke(
            FunctionName=LAMBDA_FUNCTION_NAME,
            InvocationType='RequestResponse',
            Payload=json.dumps(payload)
        )
        
        # Read the streaming response payload
        response_payload = json.loads(response['Payload'].read().decode('utf-8'))
        
        # Check if Lambda crashed or had a Function Error (e.g. OOM or initialization error)
        if 'FunctionError' in response:
            error_msg = response_payload.get('errorMessage', 'Unknown Lambda Error')
            return {
                "status": "Error",
                "stdout": "",
                "stderr": f"AWS Lambda execution failed: {error_msg}",
                "exit_code": -1,
                "time_ms": int((time.time() - start) * 1000)
            }
            
        # Ensure the response has the required fields
        if "status" not in response_payload:
            return {
                "status": "Error",
                "stdout": "",
                "stderr": f"Invalid response from Lambda: {response_payload}",
                "exit_code": -1,
                "time_ms": int((time.time() - start) * 1000)
            }
            
        return response_payload

    except (ClientError, BotoCoreError) as e:
        # Catch boto3/AWS networking errors (e.g., IAM permission denied, Lambda timeout at 10s)
        error_msg = str(e)
        if "Read timeout" in error_msg or "Task timed out" in error_msg:
            return {
                "status": "Error",
                "stdout": "",
                "stderr": "Execution timed out at the AWS layer (10.0s).",
                "exit_code": 124,
                "time_ms": int((time.time() - start) * 1000)
            }
        
        return {
            "status": "Error",
            "stdout": "",
            "stderr": f"AWS Infrastructure Error: {error_msg}",
            "exit_code": -1,
            "time_ms": int((time.time() - start) * 1000)
        }
    except Exception as e:
        return {
            "status": "Error",
            "stdout": "",
            "stderr": f"Internal API Error: {str(e)}",
            "exit_code": -1,
            "time_ms": int((time.time() - start) * 1000)
        }
