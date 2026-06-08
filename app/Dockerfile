# ── Stage 1: Build .NET template (throw away the SDK after) ──────────────────
FROM mcr.microsoft.com/dotnet/sdk:8.0-bookworm-slim AS dotnet-builder

RUN dotnet new console -o /app/csharp_template && \
    cd /app/csharp_template && \
    dotnet restore && \
    dotnet publish -c Release -o /app/csharp_template/out

# ── Stage 2: Final lean image ─────────────────────────────────────────────────
FROM python:3.12-slim-bookworm

# Only install what's truly needed at runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    bubblewrap \
    nodejs \
    npm \
    gcc \
    g++ \
    make \
    sqlite3 \
    # JDK is required to compile user-submitted Java source code
    default-jdk-headless \
    && chmod u+s /usr/bin/bwrap \
    # .NET runtime only (not SDK)
    && apt-get clean && rm -rf /var/lib/apt/lists/*

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

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]