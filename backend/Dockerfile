# Imagem única do backend: o compose sobe `api`, `worker` e `migracoes` a partir dela.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

# Hugging Face: o usuário da imagem não tem home, e o HF_HOME padrão (~/.cache) não é
# gravável; o xet gravava o cache dele ali e falhava com "Permission denied (os error 13)".
# HF_HOME vai para uma pasta do usuário da imagem; os pesos vão para o volume pelo cache_dir
# (modelo_ner.baixar_modelo); o xet fica desligado (download HTTP simples, sem um segundo
# cache de blocos do mesmo modelo).
ENV HF_HOME=/dados/hf \
    HF_HUB_DISABLE_XET=1

COPY --from=ghcr.io/astral-sh/uv:0.13.4 /uv /usr/local/bin/uv

WORKDIR /app

# Dependências primeiro, para aproveitar o cache de camadas. O grupo "ner" (transformers e
# torch CPU) é a camada 2 da anonimização (F1-37); os pesos ficam no volume de modelos e só
# entram por `buscajus modelos baixar-ner`.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --group ner --no-install-project

COPY alembic.ini ./
COPY src ./src
RUN uv sync --frozen --no-dev --group ner

RUN useradd --system --uid 10001 --no-create-home buscajus \
    && mkdir -p /dados/raw /dados/modelos /dados/hf \
    && chown -R buscajus /dados
USER buscajus

EXPOSE 8000
# --no-proxy-headers: o IP do cliente vem só de api.limite.ip_do_cliente (proxies_confiaveis),
# sem o uvicorn reescrever a conexão a partir do X-Forwarded-For (ARCHITECTURE.md, seção 12.2).
CMD ["uvicorn", "buscajus.api.app:criar_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers"]
