#!/bin/bash
set -e

# Load environment variables if .env exists to grab AWS_REGION
if [ -f .env ]; then
    export $(cat .env | grep -v '#' | awk '/=/ {print $1}')
fi

REGION=${AWS_REGION:-us-east-1}
ACCOUNT_ID=$1

if [ -z "$ACCOUNT_ID" ]; then
    echo "Error: AWS Account ID is required."
    echo "Usage: ./deploy_lambda.sh <AWS_ACCOUNT_ID>"
    echo "Example: ./deploy_lambda.sh 123456789012"
    exit 1
fi

REPO_NAME="secure-code-runner"
ECR_URI="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"

echo "==========================================="
echo "Deploying Lambda Image to AWS ECR"
echo "Region: ${REGION}"
echo "Account ID: ${ACCOUNT_ID}"
echo "Repository: ${REPO_NAME}"
echo "==========================================="

# 1. Authenticate Docker to Amazon ECR
echo "[1/5] Authenticating with AWS ECR..."
aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin $ECR_URI

# 2. Create the ECR repository if it doesn't exist
echo "[2/5] Ensuring ECR repository exists..."
aws ecr describe-repositories --repository-names $REPO_NAME --region $REGION > /dev/null 2>&1 || \
aws ecr create-repository --repository-name $REPO_NAME --region $REGION > /dev/null

# 3. Build the Docker image
echo "[3/5] Building the Lambda Docker image (this might take a few minutes)..."
cd lambda
docker build --network host -t $REPO_NAME .

# 4. Tag the image
echo "[4/5] Tagging the image..."
docker tag ${REPO_NAME}:latest ${ECR_URI}/${REPO_NAME}:latest

# 5. Push the image
echo "[5/5] Pushing the image to ECR..."
docker push ${ECR_URI}/${REPO_NAME}:latest

echo "==========================================="
echo "✅ Deployment to ECR successful!"
echo "Next step: Create or update your Lambda function to use:"
echo "${ECR_URI}/${REPO_NAME}:latest"
echo "==========================================="
