# ── Stage 1: Build .NET template (throw away the SDK after) ──────────────────
FROM mcr.microsoft.com/dotnet/sdk:8.0-bookworm-slim AS dotnet-builder

RUN dotnet new console -o /app/csharp_template && \
    cd /app/csharp_template && \
    dotnet restore && \
    dotnet publish -c Release -o /app/csharp_template/out

# ── Stage 2: Final lean image ─────────────────────────────────────────────────
FROM python:3.12-slim-bookworm

# Only install what's truly needed at runtime.
# bubblewrap: sandboxing; curl: health-check probe; ca-certificates: HTTPS trust
RUN apt-get update && apt-get install -y --no-install-recommends \
    bubblewrap \
    nodejs \
    npm \
    gcc \
    g++ \
    make \
    sqlite3 \
    curl \
    ca-certificates \
    # JDK is required to compile user-submitted Java source code
    default-jdk-headless \
    # .NET runtime only (not SDK)
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# bwrap is designed to run SUID — it is a purpose-built, security-audited
# sandboxing tool whose entire model is: start as root (via SUID), set up
# namespaces + filesystem, map unprivileged UID/GID, then exec the payload.
# Without SUID, a non-root container user (UID 10000) gets no effective
# capabilities (Linux drops caps on exec for non-root), so bwrap cannot
# write /proc/self/uid_map to create user namespaces.
# The blast radius is limited: bwrap immediately drops to UID 10000 inside
# the sandbox and the Docker container itself has restricted caps + read-only fs.
RUN chmod u+s /usr/bin/bwrap

# Copy only the .NET runtime from Microsoft (no SDK)
COPY --from=dotnet-builder /usr/share/dotnet /usr/share/dotnet
ENV PATH="$PATH:/usr/share/dotnet"
ENV DOTNET_ROOT="/usr/share/dotnet"

# Copy pre-built C# template (no dotnet restore needed at runtime)
COPY --from=dotnet-builder /app/csharp_template /app/csharp_template

RUN groupadd -g 10000 app_user && useradd -u 10000 -g 10000 -m -s /bin/bash app_user

WORKDIR /app

COPY code/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY code/app.py .

RUN chown -R app_user:app_user /app

USER app_user

EXPOSE 8000

# WORKERS env var controls uvicorn parallelism (keep at 1 for sandbox correctness)
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port 8000 --workers ${WORKERS:-1}"]