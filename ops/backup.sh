#!/bin/sh
# Backup do Postgres (F6-11): pg_dump em formato custom, rodando dentro do contêiner db (mesma
# versão do servidor). Não inclui a área temporária dos cadernos nem os arquivos brutos (que
# ficam no volume raw e são recriáveis a partir das fontes).
#
#   ops/backup.sh [diretorio]          (padrão: ./backups)
#
# Variáveis: POSTGRES_USER e POSTGRES_DB (padrão: buscajus), BACKUP_RETENCAO_DIAS (padrão: 14).
# Agendamento diário sugerido (cron do servidor): 30 3 * * * cd /srv/buscajus && ops/backup.sh
set -eu

DESTINO="${1:-./backups}"
USUARIO="${POSTGRES_USER:-buscajus}"
BANCO="${POSTGRES_DB:-buscajus}"
RETENCAO="${BACKUP_RETENCAO_DIAS:-14}"

mkdir -p "$DESTINO"
ARQUIVO="$DESTINO/$BANCO-$(date -u +%Y%m%dT%H%M%SZ).dump"
TEMPORARIO="$ARQUIVO.parcial"
trap 'rm -f "$TEMPORARIO"' EXIT

docker compose exec -T db pg_dump -U "$USUARIO" -d "$BANCO" --format=custom --no-owner \
  > "$TEMPORARIO"
mv "$TEMPORARIO" "$ARQUIVO"
sha256sum "$ARQUIVO" > "$ARQUIVO.sha256"

# Retenção: apaga backups deste banco com mais de RETENCAO dias.
find "$DESTINO" -name "$BANCO-*.dump*" -type f -mtime +"$RETENCAO" -exec rm -f {} +

echo "backup: $ARQUIVO ($(wc -c < "$ARQUIVO") bytes)"
