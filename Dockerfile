FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

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

# Drop to non-root user provided by the Playwright base image
USER pwuser

CMD ["python", "-m", "src.main"]
