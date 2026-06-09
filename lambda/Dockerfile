FROM public.ecr.aws/lambda/python:3.12

# Install dependencies via Amazon Linux 2023 DNF package manager
# AL2023 provides modern packages for nodejs, gcc, java, sqlite
RUN dnf install -y \
    nodejs \
    gcc \
    gcc-c++ \
    java-21-amazon-corretto-devel \
    sqlite \
    wget \
    tar \
    libicu \
    && dnf clean all

# Install .NET 8 SDK via official install script (AL2023 doesn't have a stable Microsoft RPM url)
RUN wget https://dot.net/v1/dotnet-install.sh -O dotnet-install.sh \
    && chmod +x dotnet-install.sh \
    && ./dotnet-install.sh --channel 8.0 --install-dir /usr/share/dotnet \
    && rm dotnet-install.sh
ENV PATH="$PATH:/usr/share/dotnet"
ENV DOTNET_ROOT="/usr/share/dotnet"
ENV DOTNET_CLI_HOME="/var/task/dotnet_home"
ENV HOME="/var/task/dotnet_home"
ENV DOTNET_CLI_TELEMETRY_OPTOUT=1
ENV DOTNET_SKIP_FIRST_TIME_EXPERIENCE=1
ENV DOTNET_NOLOGO=1
ENV MSBUILDDISABLENODEREUSE=1
# Pre-build C# console template in the Lambda task directory
# This avoids needing to run "dotnet new" or "dotnet restore" during the 10s execution window
WORKDIR ${LAMBDA_TASK_ROOT}
RUN dotnet new console -n App -o csharp_template \
    && cd csharp_template \
    && dotnet restore \
    && chmod -R 777 /var/task/dotnet_home \
    && chmod -R 777 /var/task/csharp_template

# Copy the Lambda handler code into the task root
COPY handler.py ${LAMBDA_TASK_ROOT}/

# Set the CMD to your handler
CMD ["handler.lambda_handler"]
