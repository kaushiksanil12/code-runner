#!/bin/bash
set -e

echo "Pulling executor images into the rootless podman storage..."

# Execute the pulls inside the running secure-code-runner container
# This ensures they are stored in the podman_data volume owned by app_user
docker exec -it secure-code-runner podman pull docker.io/library/python:3.12-slim
docker exec -it secure-code-runner podman pull docker.io/library/node:20-slim
docker exec -it secure-code-runner podman pull docker.io/library/openjdk:21-slim
docker exec -it secure-code-runner podman pull docker.io/library/gcc:13
docker exec -it secure-code-runner podman pull mcr.microsoft.com/dotnet/sdk:8.0
docker exec -it secure-code-runner podman pull docker.io/keinos/sqlite3

echo "All images successfully pulled into podman local storage!"
