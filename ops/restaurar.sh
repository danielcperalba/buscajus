#!/bin/sh
# Restauração de um backup (F6-11) num banco separado, para conferir ou recuperar.
#
#   ops/restaurar.sh arquivo.dump [banco_destino]     (padrão: buscajus_restauracao)
#
# Recusa restaurar por cima do banco principal (POSTGRES_DB): para substituir a base em
# produção, restaure num banco novo, confira e troque a conexão (BUSCAJUS_DATABASE_URL).
# Ao final, imprime só contagens (nenhum conteúdo).
set -eu

ARQUIVO="${1:?uso: ops/restaurar.sh arquivo.dump [banco_destino]}"
DESTINO="${2:-buscajus_restauracao}"
USUARIO="${POSTGRES_USER:-buscajus}"
PRINCIPAL="${POSTGRES_DB:-buscajus}"

if [ "$DESTINO" = "$PRINCIPAL" ]; then
  echo "recusado: o destino é o banco principal ($PRINCIPAL)" >&2
  exit 2
fi
if [ -f "$ARQUIVO.sha256" ]; then
  (cd "$(dirname "$ARQUIVO")" && sha256sum -c "$(basename "$ARQUIVO").sha256" >/dev/null)
fi

psql() { docker compose exec -T db psql -U "$USUARIO" -v ON_ERROR_STOP=1 "$@"; }

psql -d postgres -c "DROP DATABASE IF EXISTS \"$DESTINO\"" >/dev/null
psql -d postgres -c "CREATE DATABASE \"$DESTINO\"" >/dev/null
docker compose exec -T db pg_restore -U "$USUARIO" -d "$DESTINO" --no-owner --exit-on-error \
  < "$ARQUIVO"

psql -d "$DESTINO" -tA -c "
  SELECT 'acordao.' || situacao, count(*) FROM acordao GROUP BY situacao
  UNION ALL SELECT 'acordao_historico', count(*) FROM acordao_historico
  UNION ALL SELECT 'classe_cnj', count(*) FROM classe_cnj
  UNION ALL SELECT 'caderno_djen', count(*) FROM caderno_djen
  UNION ALL SELECT 'coleta_janela', count(*) FROM coleta_janela
  UNION ALL SELECT 'bloqueio', count(*) FROM bloqueio
  UNION ALL SELECT 'pedido_remocao', count(*) FROM pedido_remocao
  UNION ALL SELECT 'alembic_version=' || version_num, 1 FROM alembic_version
  ORDER BY 1"
