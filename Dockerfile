FROM python:3.10-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
RUN pip install fastapi uvicorn python-multipart
COPY . .
CMD ["python", "api.py"]