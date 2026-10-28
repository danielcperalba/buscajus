// Status HTTP real para o detalhe do acórdão (404 e 410).
//
// A página /acordao/[id] carrega em streaming (prerender parcial): quando ela descobre que o
// acórdão não existe, o status 200 já foi enviado. Este proxy roda antes da renderização e
// consulta só a situação na API (GET /api/v1/acordaos/{id}/situacao, sem o texto):
//
// - inexistente (ou id inválido) → HTML da página /nao-encontrado, com status 404;
// - cancelado ou removido → HTML da própria página de detalhe (que mostra o aviso), com 410;
// - ativo, ou API fora do ar → segue normalmente.
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

function origemLocal(): string {
  return `http://127.0.0.1:${process.env.PORT ?? "3000"}`;
}

export async function proxy(request: NextRequest) {
  if (request.method !== "GET" || request.headers.has("rsc") || request.headers.has(JA_CONFERIDO)) {
    return NextResponse.next();
  }
  const id = request.nextUrl.pathname.split("/").at(-1) ?? "";
  if (!/^\d{1,18}$/.test(id)) return paginaComStatus("/nao-encontrado", 404);

  let situacao: string | undefined;
  try {
    const resposta = await fetch(
      `${process.env.API_URL ?? URL_PADRAO}/api/v1/acordaos/${id}/situacao`,
      { cache: "no-store", signal: AbortSignal.timeout(3000) },
    );
    if (resposta.status === 404) return paginaComStatus("/nao-encontrado", 404);
    if (resposta.ok) situacao = ((await resposta.json()) as { situacao: string }).situacao;
  } catch {
    // API fora do ar: a página mostra o erro.
  }
  if (situacao === "cancelado" || situacao === "removido") {
    return paginaComStatus(`/acordao/${id}`, 410);
  }
  return NextResponse.next();
}

async function paginaComStatus(caminho: string, status: number): Promise<Response> {
  try {
    const pagina = await fetch(`${origemLocal()}${caminho}`, {
      headers: { [JA_CONFERIDO]: "1" },
      cache: "no-store",
    });
    return new Response(pagina.body, {
      status,
      headers: { "content-type": pagina.headers.get("content-type") ?? "text/html; charset=utf-8" },
    });
  } catch {
    return new Response("Não encontrado", { status });
  }
}
