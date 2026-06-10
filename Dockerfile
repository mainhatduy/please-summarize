FROM python:3.11-slim

# Ngăn Python tạo *.pyc và đệm stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DATA_DIR=/data

WORKDIR /bot

COPY requirements.txt .

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir -r requirements.txt

RUN mkdir -p /data

COPY app/ ./app/

# Chạy bot
CMD ["python", "-m", "app.main"]
