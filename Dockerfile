FROM python:3.12-slim

# System deps for reportlab, python-docx, python-pptx, and general build
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    libxml2-dev \
    libxslt-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy only what's needed to build the package
COPY pyproject.toml README.md LICENSE ./
COPY src/ src/
COPY api/ api/

# Upgrade pip, then install opendocs with all runtime extras
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -e ".[api,templates,publish]"

# Create a non-root user for security
RUN adduser --disabled-password --gecos '' appuser \
 && chown -R appuser /app
USER appuser

# Railway injects $PORT at runtime
ENV PORT=8080
EXPOSE 8080

# Start uvicorn
CMD ["sh", "-c", "uvicorn api.server:app --host 0.0.0.0 --port ${PORT:-8080} --workers 2"]
