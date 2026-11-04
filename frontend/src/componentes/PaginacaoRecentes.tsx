import Link from "next/link";

import { urlRecentes } from "@/lib/recentes";

type Props = { pagina: number; totalPaginas: number };

/**
 * Anterior e Próxima, com "Página X de Y" no meio, sem lista de números (F5-13). Na primeira e
 * na última página o botão vira texto com ``aria-disabled``, como na paginação da busca.
 */
export function PaginacaoRecentes({ pagina, totalPaginas }: Props) {
  if (totalPaginas <= 1) return null;
  return (
    <nav className="paginacao paginacao-recentes" aria-label="Páginas de acórdãos recentes">
      <ul>
        <li>
          {pagina > 1 ? (
            <Link href={urlRecentes(pagina - 1)} rel="prev">
              Anterior
            </Link>
          ) : (
            <span aria-disabled="true">Anterior</span>
          )}
        </li>
        <li className="paginacao-posicao">{`Página ${pagina} de ${totalPaginas}`}</li>
        <li>
          {pagina < totalPaginas ? (
            <Link href={urlRecentes(pagina + 1)} rel="next">
              Próxima
            </Link>
          ) : (
            <span aria-disabled="true">Próxima</span>
          )}
        </li>
      </ul>
    </nav>
  );
}
