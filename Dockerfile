FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    DIZIONE_DATA=/app/weights/phonemizer TINY_VOCA_FRONTEND=own \
    OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 HF_HUB_DISABLE_TELEMETRY=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates libgomp1 libsndfile1 \
    && rm -rf /var/lib/apt/lists/*
RUN python -m pip install --no-cache-dir torch==2.15.0 --index-url https://download.pytorch.org/whl/cpu
COPY . .
RUN python -m pip install --no-cache-dir . -r voice_studio/requirements.txt \
    'dizione @ git+https://github.com/n4ze3m/dizione@8cd889e4de7be6bd1dd2e6891344a0729fa14dd4' \
    && python -m voice_studio.fetch_model \
    && useradd --create-home studio
USER studio
EXPOSE 8080
CMD ["sh", "-c", "exec python -m uvicorn voice_studio.app:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1 --no-access-log"]
