FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Libs essenciais: build-essential (compilacoes nativas de wheels) e fontes
# usadas pela geracao de DOCX.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        fonts-dejavu fonts-liberation \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt
COPY . .

ENV PORT=8000
EXPOSE 8000
# --proxy-headers + --forwarded-allow-ips="*": atras do proxy Render, preserva esquema HTTPS
# --timeout-keep-alive 120: exports DOCX podem levar 1-2min; evita queda do worker
# --workers 2: rotas sync (def) vao para threadpool do Starlette automaticamente,
# mas 2 workers dao paralelismo real entre requests pesados (export DOCX ~1-2min).
# Cada worker gasta ~200-400MB; no plano Standard (2GB) 2 workers e seguro.
CMD ["sh","-c","uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 2 --proxy-headers --forwarded-allow-ips=* --timeout-keep-alive 120"]
