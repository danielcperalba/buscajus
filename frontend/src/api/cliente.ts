// Cliente tipado da API (F5-01), usado só no servidor: as páginas buscam os dados no servidor
// do Next.js, e o navegador nunca fala direto com a API.
//
// A URL vem de API_URL (no compose: http://api:8000), lida em tempo de execução. O IP do
// usuário segue em X-Forwarded-For, para o limite de taxa da API valer por pessoa, e não
// para o servidor do Next.js inteiro (a API precisa de api.confiar_x_forwarded_for = true).
import createClient from "openapi-fetch";
import { headers } from "next/headers";

import type { components, paths } from "./esquema";

export type Esquemas = components["schemas"];
export type ResultadoBusca = Esquemas["ResultadoBusca"];
export type RespostaBusca = Esquemas["RespostaBusca"];
export type DetalheAcordao = Esquemas["DetalheAcordao"];
export type Indisponivel = Esquemas["Indisponivel"];
export type AcordaosDoProcesso = Esquemas["AcordaosDoProcesso"];
export type Filtros = Esquemas["Filtros"];
export type Relator = Esquemas["Relator"];
export type ConsultaBusca = NonNullable<paths["/api/v1/busca"]["get"]["parameters"]["query"]>;

export type FalhaApi = {
  status: number;
  erro: string;
  mensagem: string;
};

export type Resposta<T> = { dados: T; falha?: undefined } | { dados?: undefined; falha: FalhaApi };

const URL_PADRAO = "http://127.0.0.1:8000";

async function cliente() {
  const recebidos = await headers();
  const encaminhar = recebidos.get("x-forwarded-for") ?? recebidos.get("x-real-ip");
  return createClient<paths>({
    baseUrl: process.env.API_URL ?? URL_PADRAO,
    headers: encaminhar ? { "x-forwarded-for": encaminhar } : {},
    cache: "no-store",
  });
}

function falha(status: number, corpo: unknown): FalhaApi {
  if (corpo && typeof corpo === "object" && "erro" in corpo && "mensagem" in corpo) {
    return { status, erro: String(corpo.erro), mensagem: String(corpo.mensagem) };
  }
  return { status, erro: "erro_inesperado", mensagem: "a API respondeu de forma inesperada" };
}

/** Executa uma chamada e converte erro de rede ou de HTTP em ``FalhaApi``. */
async function chamar<T>(
  executar: () => Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<Resposta<T>> {
  try {
    const { data, error, response } = await executar();
    if (data !== undefined && response.ok) {
      return { dados: data };
    }
    return { falha: falha(response.status, error) };
  } catch {
    return {
      falha: { status: 0, erro: "indisponivel", mensagem: "não foi possível falar com a API" },
    };
  }
}

export async function buscar(consulta: ConsultaBusca): Promise<Resposta<RespostaBusca>> {
  const api = await cliente();
  return chamar(() => api.GET("/api/v1/busca", { params: { query: consulta } }));
}

export async function obterFiltros(): Promise<Resposta<Filtros>> {
  const api = await cliente();
  return chamar(() => api.GET("/api/v1/filtros"));
}

export async function sugerirRelatores(prefixo: string): Promise<Resposta<Relator[]>> {
  const api = await cliente();
  return chamar(() => api.GET("/api/v1/relatores", { params: { query: { prefixo } } }));
}
