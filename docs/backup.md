# Backup e restauração (F6-11)

## Backup diário

`ops/backup.sh [diretório]` roda `pg_dump` (formato custom, sem dono) **dentro do contêiner `db`**, com a mesma versão do servidor, e grava `{banco}-{AAAAMMDDThhmmssZ}.dump` mais o `.sha256`. Backups com mais de `BACKUP_RETENCAO_DIAS` (padrão 14) são apagados.

- O backup não inclui a área temporária dos cadernos (tmpfs) nem os arquivos brutos do volume `raw`, que são recriáveis a partir das fontes.
- Guarde os backups em outro disco ou host; a cópia externa está em [implantacao.md](implantacao.md#cópia-fora-do-servidor).
- **Em produção**, o serviço `backup` do `compose.prod.yaml` (`ops/backup-servico.sh`, F8-04) faz o mesmo dump todo dia às `BACKUP_HORA_UTC`, com retenção `BACKUP_RETENCAO_DIAS`, em `BACKUP_DIR`; não é preciso cron. `ops/backup.sh` fica para backups avulsos (antes de uma atualização, por exemplo).
- O `.sha256` guarda só o nome do arquivo: confira dentro do diretório (`sha256sum -c arquivo.dump.sha256`).

## Restauração

`ops/restaurar.sh arquivo.dump [banco_destino]` confere o `.sha256`, recria o banco de destino (padrão `buscajus_restauracao`) e roda `pg_restore`. No fim, imprime só contagens. O script **recusa** restaurar por cima do banco principal (`POSTGRES_DB`).

Para recuperar a produção: restaure num banco novo, confira as contagens, pare `api` e `worker`, aponte `BUSCAJUS_DATABASE_URL` para o banco restaurado e suba de novo.

## Teste de restauração (27/10/2026)

Executado uma vez, no Postgres do Compose de desenvolvimento, só com dados sintéticos:

1. Banco descartável `buscajus_backup_teste`, migrações até a 0007 e 50 acórdãos sintéticos (45 ativos, 5 cancelados), mais um bloqueio.
2. `POSTGRES_DB=buscajus_backup_teste ops/backup.sh`: dump de 50.895 bytes.
3. `ops/restaurar.sh <dump> buscajus_restauracao`: contagens iguais às da origem (45 ativos, 5 cancelados, 849 classes da TPU, 1 bloqueio, `alembic_version = 0007`).
4. Impressão digital (`md5` das linhas de `acordao`: id, fonte, id_fonte, número, ementa, situação, hash e versão) igual na origem e no restaurado.
5. A configuração de texto `pt_unaccent` veio junto (`to_tsvector('pt_unaccent', 'Herança')` = `'heranc':1`).
6. Restaurar com o destino igual ao banco principal foi recusado (código 2).
7. Os dois bancos e o dump foram apagados ao fim.

Repita o teste depois de mudanças grandes no esquema e, em produção, periodicamente, com um backup real restaurado num banco separado (só contagens na saída).
