FROM python:3.13-slim

# System deps the pipeline needs at import/run time:
#  - tesseract-ocr + eng/mar/hin/osd lang packs (Tier-1 OCR)
#  - libgl1 + libglib2.0-0 (OpenCV runtime)
#  - libzbar0 (pyzbar QR decode)
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-eng \
        tesseract-ocr-mar \
        tesseract-ocr-hin \
        tesseract-ocr-osd \
        libgl1 \
        libglib2.0-0 \
        libzbar0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
RUN pip install --no-cache-dir uv
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev || uv sync --no-dev
COPY . .
EXPOSE 8000
CMD ["uv", "run", "uvicorn", "cloud.app:app", "--host", "0.0.0.0", "--port", "8000"]
