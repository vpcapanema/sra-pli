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
CMD ["sh","-c","uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
