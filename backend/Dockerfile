# Imagem única do backend: o compose sobe `api`, `worker` e `migracoes` a partir dela.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

COPY --from=ghcr.io/astral-sh/uv:0.13.4 /uv /usr/local/bin/uv

WORKDIR /app

# Dependências primeiro, para aproveitar o cache de camadas.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project

COPY alembic.ini ./
COPY src ./src
RUN uv sync --frozen --no-dev

RUN useradd --system --uid 10001 --no-create-home buscajus \
    && mkdir -p /dados/raw /dados/modelos \
    && chown -R buscajus /dados
USER buscajus

EXPOSE 8000
# --no-proxy-headers: o IP do cliente vem só de api.limite.ip_do_cliente (proxies_confiaveis),
# sem o uvicorn reescrever a conexão a partir do X-Forwarded-For (ARCHITECTURE.md, seção 12.2).
CMD ["uvicorn", "buscajus.api.app:criar_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers"]
