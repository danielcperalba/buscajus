// Tipos da API gerados a partir do contrato versionado (F5-01).
//
//   node scripts/api.mjs              regenera src/api/esquema.ts a partir de openapi.json
//   node scripts/api.mjs --verificar  falha se o arquivo não bate com o contrato
//
// O openapi.json vem do backend (`uv run buscajus api openapi > ../frontend/openapi.json`).
// O build roda a verificação: contrato novo sem regenerar os tipos quebra o build.
import { readFile, writeFile } from "node:fs/promises";
import openapiTS, { astToString } from "openapi-typescript";

const CONTRATO = new URL("../openapi.json", import.meta.url);
const DESTINO = new URL("../src/api/esquema.ts", import.meta.url);
const CABECALHO =
  "// Gerado por scripts/api.mjs a partir de openapi.json. Não edite à mão.\n" +
  "// Para regenerar: pnpm api:gerar\n\n";

const gerado = CABECALHO + astToString(await openapiTS(CONTRATO));

if (process.argv.includes("--verificar")) {
  const atual = await readFile(DESTINO, "utf8").catch(() => "");
  if (atual !== gerado) {
    console.error(
      "src/api/esquema.ts não corresponde a openapi.json: rode `pnpm api:gerar` e versione.",
    );
    process.exit(1);
  }
  console.log("tipos da API em dia com openapi.json");
} else {
  await writeFile(DESTINO, gerado);
  console.log("src/api/esquema.ts gerado");
}
