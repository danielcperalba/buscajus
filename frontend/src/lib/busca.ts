// Estado da busca na URL (/busca?q=…&tribunal=…&pagina=…) e utilidades de exibição.
import type { ConsultaBusca } from "@/api/cliente";

export const LIMITE_RESULTADOS = 200;
export const POR_PAGINA = 20;
export const MAXIMO_PAGINAS = LIMITE_RESULTADOS / POR_PAGINA;

export const EXEMPLOS = [
  "disputa por herança familiar",
  "plano de saúde negou cirurgia urgente",
  "voo cancelado sem assistência da companhia aérea",
  "pensão alimentícia atrasada",
  "nome negativado por dívida já paga",
];

export type ParametrosUrl = Record<string, string | string[] | undefined>;

export type EstadoBusca = {
  q: string;
  tribunal?: string;
  orgao?: string;
  classe?: string;
  relator?: string;
  data_inicio?: string;
  data_fim?: string;
  pagina: number;
};

const FILTROS = ["tribunal", "orgao", "classe", "relator", "data_inicio", "data_fim"] as const;
export type NomeFiltro = (typeof FILTROS)[number];

function unico(valor: string | string[] | undefined): string | undefined {
  const texto = (Array.isArray(valor) ? valor[0] : valor)?.trim();
  return texto ? texto : undefined;
}

/** Lê o estado da busca dos parâmetros da URL, descartando valores inválidos. */
export function lerEstado(parametros: ParametrosUrl): EstadoBusca {
  const estado: EstadoBusca = { q: unico(parametros.q) ?? "", pagina: 1 };
  for (const nome of FILTROS) {
    const valor = unico(parametros[nome]);
    if (valor !== undefined) estado[nome] = valor;
  }
  if (estado.classe !== undefined && !/^\d+$/.test(estado.classe)) delete estado.classe;
  for (const data of ["data_inicio", "data_fim"] as const) {
    if (estado[data] !== undefined && !/^\d{4}-\d{2}-\d{2}$/.test(estado[data])) {
      delete estado[data];
    }
  }
  const pagina = Number(unico(parametros.pagina));
  if (Number.isInteger(pagina) && pagina >= 1 && pagina <= MAXIMO_PAGINAS) estado.pagina = pagina;
  return estado;
}

/** Parâmetros da chamada à API a partir do estado da URL. */
export function consultaApi(estado: EstadoBusca): ConsultaBusca {
  return {
    q: estado.q,
    tribunal: estado.tribunal,
    orgao: estado.orgao,
    classe: estado.classe !== undefined ? Number(estado.classe) : undefined,
    relator: estado.relator,
    data_inicio: estado.data_inicio,
    data_fim: estado.data_fim,
    pagina: estado.pagina,
  };
}

/** URL de /busca com o estado e as alterações (``undefined`` remove o parâmetro). */
export function urlBusca(
  estado: EstadoBusca,
  alteracoes: Partial<Record<keyof EstadoBusca, string | number | undefined>> = {},
): string {
  const parametros = new URLSearchParams();
  const combinado: Record<string, string | number | undefined> = { ...estado, ...alteracoes };
  for (const nome of ["q", ...FILTROS, "pagina"] as const) {
    const valor = combinado[nome];
    if (valor === undefined || valor === "") continue;
    if (nome === "pagina" && Number(valor) === 1) continue;
    parametros.set(nome, String(valor));
  }
  return `/busca?${parametros.toString()}`;
}

export function filtrosAtivos(estado: EstadoBusca): NomeFiltro[] {
  return FILTROS.filter((nome) => estado[nome] !== undefined);
}

/**
 * O trecho vem da API com o texto escapado e ``<mark>`` em volta dos termos. Por defesa, só
 * ``<mark>`` e ``</mark>`` sobrevivem: qualquer outro ``<`` vira texto.
 */
export function trechoSeguro(trecho: string): string {
  return trecho.replace(/<(?!\/?mark>)/g, "&lt;");
}

/** ``2026-10-08`` → ``08/10/2026``. */
export function formatarData(iso: string | null | undefined): string | undefined {
  const partes = iso ? /^(\d{4})-(\d{2})-(\d{2})/.exec(iso) : null;
  return partes ? `${partes[3]}/${partes[2]}/${partes[1]}` : undefined;
}
