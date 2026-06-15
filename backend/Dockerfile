# Lol-AI-lo backend image.
# Lean python:3.11-slim base. The app is designed to start with zero external
# services configured (see backend/main.py + SPEC readiness matrix), so the
# image only needs the Python deps plus a couple of optional system packages.
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System packages:
#   - build-essential: some wheels (PyMuPDF, llama-index deps) may need a
#     compiler if a prebuilt wheel is unavailable for the platform.
#   - tesseract-ocr: OPTIONAL. Only needed for OCR of *scanned* PDF precedents
#     (pytesseract). Without it, scanned PDFs are simply skipped as RAG context
#     and everything else works. Comment this line out for a smaller image if
#     you don't need scanned-PDF OCR.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first for better layer caching.
COPY requirements.txt ./
RUN pip install -r requirements.txt

# Copy application code.
COPY . .

# Local filesystem precedent store (used when Google Drive is not configured).
# Mounted as a volume by docker-compose so generated docs/precedents persist.
RUN mkdir -p /app/storage
ENV LOCAL_STORAGE_DIR=/app/storage

EXPOSE 8000

# host 0.0.0.0 so the container is reachable from the host / other containers.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
