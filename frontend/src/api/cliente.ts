// Cliente tipado da API (F5-01), usado só no servidor: as páginas buscam os dados no servidor
// do Next.js, e o navegador nunca fala direto com a API.
//
// A URL vem de API_URL (no compose: http://api:8000), lida em tempo de execução. O IP do
// usuário segue para a API em X-Forwarded-For, para o limite de taxa valer por pessoa: só o
// último item recebido, o que o proxy reverso (Caddy) acrescentou; os anteriores vêm do
// cliente e podem ser falsificados. Em produção, só o Caddy é exposto (ARCHITECTURE 12.2).
import createClient from "openapi-fetch";
import { headers } from "next/headers";

import { ipAcrescentadoPeloProxy } from "@/lib/ip";

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
  const encaminhar = ipAcrescentadoPeloProxy((await headers()).get("x-forwarded-for"));
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

export type PedidoRemocao = Esquemas["PedidoRemocao"];
export type RemocaoRecebida = Esquemas["RemocaoRecebida"];

/** Detalhe; 410 (cancelado ou removido) vem em ``falha`` com o corpo ``Indisponivel``. */
export async function obterDetalhe(
  id: number,
): Promise<Resposta<DetalheAcordao> & { indisponivel?: Indisponivel }> {
  const api = await cliente();
  try {
    const { data, error, response } = await api.GET("/api/v1/acordaos/{acordao_id}", {
      params: { path: { acordao_id: id } },
    });
    if (data !== undefined && response.ok) return { dados: data };
    if (response.status === 410 && error && typeof error === "object" && "erro" in error) {
      const indisponivel = error as Indisponivel;
      return {
        falha: { status: 410, erro: indisponivel.erro, mensagem: indisponivel.mensagem },
        indisponivel,
      };
    }
    return { falha: falha(response.status, error) };
  } catch {
    return {
      falha: { status: 0, erro: "indisponivel", mensagem: "não foi possível falar com a API" },
    };
  }
}

export async function obterProcesso(numero: string): Promise<Resposta<AcordaosDoProcesso>> {
  const api = await cliente();
  return chamar(() => api.GET("/api/v1/processos/{numero}", { params: { path: { numero } } }));
}

export async function registrarRemocao(pedido: PedidoRemocao): Promise<Resposta<RemocaoRecebida>> {
  const api = await cliente();
  return chamar(() => api.POST("/api/v1/remocao", { body: pedido }));
}

export type CoberturaTribunal = Esquemas["CoberturaTribunal"];

export async function obterCobertura(): Promise<Resposta<CoberturaTribunal[]>> {
  const api = await cliente();
  return chamar(() => api.GET("/api/v1/cobertura"));
}
