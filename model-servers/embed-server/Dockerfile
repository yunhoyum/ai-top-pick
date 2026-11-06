FROM python:3.12-slim

# 로그를 바로 출력하고 .pyc 파일을 만들지 않는다
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HOME=/models/hf

WORKDIR /app

# torch를 먼저 설치한다. 용량이 커서(수 GB) 별도 단계로 두면 캐시로 건너뛰기 쉽다
RUN pip install --no-cache-dir torch==2.15.0

# requirements.txt를 먼저 복사한다. 코드만 바뀌면 설치 단계를 캐시로 건너뛴다
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 0.0.0.0이어야 컨테이너 밖에서 접속할 수 있다 (uvicorn 기본값은 127.0.0.1)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]