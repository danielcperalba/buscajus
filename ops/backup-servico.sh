#!/bin/sh
# Serviço de backup do compose de produção (F8-04). Roda no contêiner "backup" (imagem do
# Postgres, mesmo pg_dump do servidor), conectado ao db pela rede interna:
#
# - um backup ao subir, se não houver um bem-sucedido nas últimas 24 horas;
# - depois, um por dia às BACKUP_HORA_UTC (padrão 06:30 UTC = 03:30 em Brasília);
# - apaga os backups com mais de BACKUP_RETENCAO_DIAS (padrão 14).
#
# Grava {banco}-{AAAAMMDDThhmmssZ}.dump e .sha256 em /backups (BACKUP_DIR no host) e marca
# /backups/.ultimo-backup, usado pelo healthcheck. Conexão por PGHOST, PGUSER, PGPASSWORD e
# PGDATABASE. A cópia para fora do servidor está em docs/implantacao.md.
set -eu

DESTINO=/backups
HORA="${BACKUP_HORA_UTC:-06:30}"
RETENCAO="${BACKUP_RETENCAO_DIAS:-14}"
MARCA="$DESTINO/.ultimo-backup"
umask 077

case "$HORA" in
  [01][0-9]:[0-5][0-9] | 2[0-3]:[0-5][0-9]) ;;
  *) echo "backup: BACKUP_HORA_UTC inválida (use HH:MM)" >&2; exit 2 ;;
esac

fazer_backup() {
  nome="$PGDATABASE-$(date -u +%Y%m%dT%H%M%SZ).dump"
  if pg_dump --format=custom --no-owner --file="$DESTINO/$nome.parcial"; then
    mv "$DESTINO/$nome.parcial" "$DESTINO/$nome"
    (cd "$DESTINO" && sha256sum "$nome" > "$nome.sha256")
    touch "$MARCA"
    find "$DESTINO" -name "$PGDATABASE-*.dump*" -type f -mtime +"$RETENCAO" -exec rm -f {} +
    echo "backup: $nome ($(wc -c < "$DESTINO/$nome") bytes)"
  else
    rm -f "$DESTINO/$nome.parcial"
    echo "backup: pg_dump falhou" >&2
  fi
}

if [ -z "$(find "$MARCA" -mmin -1440 2>/dev/null)" ]; then
  fazer_backup
fi

ultimo_dia=""
while :; do
  if [ "$(date -u +%H:%M)" = "$HORA" ] && [ "$(date -u +%F)" != "$ultimo_dia" ]; then
    ultimo_dia="$(date -u +%F)"
    fazer_backup
  fi
  sleep 20
done
