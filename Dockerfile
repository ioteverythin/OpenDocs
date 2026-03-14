FROM python:3.12-slim

# System deps for reportlab, python-docx, python-pptx
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy project files
COPY pyproject.toml README.md LICENSE ./
COPY src/ src/
COPY api/ api/

# Install opendocs + API deps
RUN pip install --no-cache-dir -e ".[api,templates]"

# Port (Railway sets $PORT)
ENV PORT=8080
EXPOSE 8080

# Start uvicorn
CMD ["sh", "-c", "uvicorn api.server:app --host 0.0.0.0 --port ${PORT:-8080}"]
