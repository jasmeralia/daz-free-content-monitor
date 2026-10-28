FROM mcr.microsoft.com/playwright/python:v1.64.1-noble

WORKDIR /app

# Ensure stdout/stderr are unbuffered so logs appear immediately in Dozzle/Docker
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install only Chromium to keep image size manageable
RUN playwright install chromium --with-deps

COPY src/ ./src/
COPY scripts/ ./scripts/

# Persistent data directory (mount as volume at runtime)
RUN mkdir -p /app/data

# Match the UID/GID that own the TrueNAS data directory and mode-600 .env file.
USER 1000:1000

CMD ["python", "-m", "src.main"]
