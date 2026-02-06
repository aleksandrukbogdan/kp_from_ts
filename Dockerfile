# NVIDIA PyTorch image with CUDA support for H100
# Using 2.3.1 because docling requires torch >= 2.2.2
FROM pytorch/pytorch:2.3.1-cuda12.1-cudnn8-runtime

# Install system dependencies for Docling, OCR, and DOCX conversion
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    tesseract-ocr \
    poppler-utils \
    libreoffice-writer \
    && rm -rf /var/lib/apt/lists/*


WORKDIR /app

# 1. Install heavy dependencies (Cached Layer)
COPY requirements-core.txt .
RUN pip install --no-cache-dir -r requirements-core.txt

# 2. Install app dependencies (Frequent changes)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Ensure uvicorn is installed for the API
RUN pip install uvicorn

COPY . .

# Default command (can be overridden by docker-compose)
CMD ["python", "api.py"]