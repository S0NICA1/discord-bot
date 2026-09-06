FROM python:3.11-slim

# تثبيت libopus0 و ffmpeg (مطلوب لصوت الديسكورد)
RUN apt-get update && \
    apt-get install -y --no-install-recommends libopus0 ffmpeg && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]
