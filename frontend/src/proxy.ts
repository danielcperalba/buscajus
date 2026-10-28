// Status HTTP real para o detalhe do acórdão (404, 410 e 503).
//
// A página /acordao/[id] carrega em streaming (prerender parcial): quando ela descobre que o
// acórdão não existe, o status 200 já foi enviado. Este proxy roda antes da renderização e
// consulta só a situação na API (GET /api/v1/acordaos/{id}/situacao, sem o texto):
//
// - inexistente (ou id inválido) → HTML da página /nao-encontrado, com status 404;
// - cancelado ou removido → HTML da própria página de detalhe (que mostra o aviso), com 410;
// - API fora do ar, lenta (acima de API_TIMEOUT_SITUACAO_MS) ou com erro → HTML de
//   /indisponivel, com 503 e Retry-After, sem nenhum detalhe do erro;
// - ativo → segue normalmente.
//
// A reescrita do Next não aplica outro status; por isso o proxy busca o HTML no próprio
// servidor (127.0.0.1) e responde com o status certo. Navegações internas do roteador
// (cabeçalho RSC) e Server Actions seguem sem conferência: o status só importa para
// documentos (buscadores, links externos).
import { type NextRequest, NextResponse } from "next/server";

export const config = { matcher: "/acordao/:id" };

const URL_PADRAO = "http://127.0.0.1:8000";
// Marca as requisições que o próprio proxy faz, para não conferir de novo.
const JA_CONFERIDO = "x-buscajus-situacao-conferida";
const TIMEOUT_PADRAO_MS = 3000;
const SEGUNDOS_PARA_TENTAR_DE_NOVO = "30";

function milissegundos(valor: string | undefined, padrao: number): number {
  const numero = Number(valor);
  return Number.isFinite(numero) && numero > 0 ? numero : padrao;
}

function origemLocal(): string {
  return `http://127.0.0.1:${process.env.PORT ?? "3000"}`;
}

type Situacao = "ativo" | "cancelado" | "removido" | "inexistente" | "indisponivel";

async function consultarSituacao(id: string): Promise<Situacao> {
  const limite = milissegundos(process.env.API_TIMEOUT_SITUACAO_MS, TIMEOUT_PADRAO_MS);
  try {
    const resposta = await fetch(
      `${process.env.API_URL ?? URL_PADRAO}/api/v1/acordaos/${id}/situacao`,
      { cache: "no-store", signal: AbortSignal.timeout(limite) },
    );
    if (resposta.status === 404) return "inexistente";
    if (!resposta.ok) return "indisponivel";
    const { situacao } = (await resposta.json()) as { situacao?: unknown };
    return situacao === "ativo" || situacao === "cancelado" || situacao === "removido"
      ? situacao
      : "indisponivel";
  } catch {
    // Rede, timeout ou corpo inesperado: nada do erro vai para a resposta.
    return "indisponivel";
  }
}

export async function proxy(request: NextRequest) {
  if (request.method !== "GET" || request.headers.has("rsc") || request.headers.has(JA_CONFERIDO)) {
    return NextResponse.next();
  }
  const id = request.nextUrl.pathname.split("/").at(-1) ?? "";
  if (!/^\d{1,18}$/.test(id)) return paginaComStatus("/nao-encontrado", 404);

  switch (await consultarSituacao(id)) {
    case "inexistente":
      return paginaComStatus("/nao-encontrado", 404);
    case "cancelado":
    case "removido":
      return paginaComStatus(`/acordao/${id}`, 410);
    case "indisponivel":
      return paginaComStatus("/indisponivel", 503, {
        "retry-after": SEGUNDOS_PARA_TENTAR_DE_NOVO,
      });
    default:
      return NextResponse.next();
  }
}

const TEXTO_SIMPLES: Record<number, string> = {
  404: "Acórdão não encontrado.",
  410: "Acórdão indisponível.",
  503: "Serviço temporariamente indisponível. Tente de novo em instantes.",
};

async function paginaComStatus(
  caminho: string,
  status: number,
  extras: Record<string, string> = {},
): Promise<Response> {
  const limite = milissegundos(process.env.API_TIMEOUT_SITUACAO_MS, TIMEOUT_PADRAO_MS);
  try {
    const pagina = await fetch(`${origemLocal()}${caminho}`, {
      headers: { [JA_CONFERIDO]: "1" },
      cache: "no-store",
      signal: AbortSignal.timeout(limite),
    });
    return new Response(pagina.body, {
      status,
      headers: {
        "content-type": pagina.headers.get("content-type") ?? "text/html; charset=utf-8",
        "cache-control": "no-store",
        ...extras,
      },
    });
  } catch {
    // Nem a página local respondeu: texto simples, com o mesmo status.
    return new Response(TEXTO_SIMPLES[status] ?? "Erro.", {
      status,
      headers: {
        "content-type": "text/plain; charset=utf-8",
        "cache-control": "no-store",
        ...extras,
      },
    });
  }
}
