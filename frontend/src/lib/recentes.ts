// Página da lista de acórdãos recentes na URL da página inicial (/?pagina=N; F5-13).
import type { ParametrosUrl } from "@/lib/busca";

export const MAXIMO_PAGINAS_RECENTES = 100;
// Âncora da seção: a navegação entre páginas volta para a lista, não para o topo.
export const ANCORA_RECENTES = "acordaos-recentes";

/** Página pedida na URL; qualquer valor inválido ou fora do limite vira a página 1. */
export function lerPaginaRecentes(parametros: ParametrosUrl): number {
  const valor = Array.isArray(parametros.pagina) ? parametros.pagina[0] : parametros.pagina;
  const texto = valor?.trim() ?? "";
  if (!/^\d+$/.test(texto)) return 1;
  const pagina = Number(texto);
  return pagina >= 1 && pagina <= MAXIMO_PAGINAS_RECENTES ? pagina : 1;
}

/** ``/`` para a primeira página e ``/?pagina=N`` para as outras, com a âncora da seção. */
export function urlRecentes(pagina: number): string {
  return `${pagina > 1 ? `/?pagina=${pagina}` : "/"}#${ANCORA_RECENTES}`;
}
