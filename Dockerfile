FROM python:3.11-slim

# ffmpeg 설치
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 의존성 먼저 설치 (캐시 활용)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 앱 복사
COPY . .

# 작업 디렉토리 생성
RUN mkdir -p assets scripts output

# HuggingFace Spaces는 7860 포트 사용
ENV PORT=7860
EXPOSE 7860

CMD ["python", "server.py"]
