FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --no-cache-dir flask yt-dlp gunicorn

COPY app.py index.html login.html ./

ENV DOWNLOAD_DIR=/data/downloads
ENV PORT=5000

EXPOSE 5000

CMD ["sh", "-c", "gunicorn -w 1 --threads 8 -b 0.0.0.0:${PORT} app:app"]
