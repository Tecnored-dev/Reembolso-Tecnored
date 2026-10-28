# ---------------------------------------------------------------------------
# Build stage
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---------------------------------------------------------------------------
# Runtime stage
# ---------------------------------------------------------------------------
FROM python:3.12-slim

WORKDIR /app

# Leitura automática de comprovantes (OCR, roda tudo aqui dentro, nada sai do
# servidor): Tesseract com o português. Antes do COPY do código para ficar em
# cache entre os deploys.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-por \
    && rm -rf /var/lib/apt/lists/*

# Cada leitura usa um núcleo só: o servidor é compartilhado com outros sistemas
# (o limite de leituras ao mesmo tempo fica em app/config.py).
ENV OMP_THREAD_LIMIT=1

COPY --from=builder /install /usr/local

# Código da aplicação — testes, caches e requirements-dev ficam de fora
# pelo .dockerignore. VERSION/RELEASE_DATE/COMMIT_HASH entram quando existirem
# (o semantic-release cria no primeiro release; antes disso há fallback).
COPY . .

# /data: volume com os arquivos das notas enquanto o storage for "local"
# (sobrescrito pelo volume em runtime).
RUN mkdir -p /data

RUN useradd -m appuser && chown -R appuser:appuser /app /data
USER appuser

EXPOSE 8000

# Migrations antes de subir a API: o banco (TUPSRVDB02 em hml/main, container
# local em dev) fica sempre no schema que este código espera. Uma réplica só
# (padrão do Dokploy aqui), então não há corrida entre dois "upgrade head".
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
