FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Ensure uvicorn is installed for the API
RUN pip install uvicorn

COPY . .

# Default command (can be overridden by docker-compose)
CMD ["python", "api.py"]