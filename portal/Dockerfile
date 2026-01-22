FROM python:3.10-slim

WORKDIR /app

# Копируем только то, что нужно для портала
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем содержимое папки portal в корень /app контейнера
COPY portal/ .

EXPOSE 5000

CMD ["python", "portal_app.py"]
