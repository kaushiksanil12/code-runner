FROM public.ecr.aws/lambda/python:3.12

# Install dependencies via Amazon Linux 2023 DNF package manager
# AL2023 provides modern packages for nodejs, gcc, java, sqlite
RUN dnf install -y \
    nodejs \
    gcc \
    gcc-c++ \
    java-21-amazon-corretto-headless \
    sqlite \
    wget \
    tar \
    && dnf clean all

# Install .NET 8 SDK
# AL2023 requires the Microsoft package repository for .NET 8
RUN rpm -Uvh https://packages.microsoft.com/config/al2023/packages-microsoft-prod.rpm \
    && dnf install -y dotnet-sdk-8.0 \
    && dnf clean all

# Pre-build C# console template in the Lambda task directory
# This avoids needing to run "dotnet new" or "dotnet restore" during the 10s execution window
WORKDIR ${LAMBDA_TASK_ROOT}
RUN dotnet new console -n App -o csharp_template \
    && cd csharp_template \
    && dotnet restore

# Copy the Lambda handler code into the task root
COPY handler.py ${LAMBDA_TASK_ROOT}/

# Set the CMD to your handler
CMD ["handler.lambda_handler"]
