import Link from "next/link";

import { type EstadoBusca, POR_PAGINA, urlBusca } from "@/lib/busca";

type Props = { estado: EstadoBusca; total: number };

/** Páginas de 20, até o limite de 200 resultados (F5-07). */
export function Paginacao({ estado, total }: Props) {
  const paginas = Math.ceil(total / POR_PAGINA);
  if (paginas <= 1) return null;
  const atual = estado.pagina;
  return (
    <nav className="paginacao" aria-label="Páginas de resultados">
      <ul>
        <li>
          {atual > 1 ? (
            <Link href={urlBusca(estado, { pagina: atual - 1 })} rel="prev">
              Anterior
            </Link>
          ) : (
            <span aria-disabled="true">Anterior</span>
          )}
        </li>
        {Array.from({ length: paginas }, (_, i) => i + 1).map((numero) => (
          <li key={numero}>
            {numero === atual ? (
              <span aria-current="page">
                <span className="visualmente-oculto">Página </span>
                {numero}
              </span>
            ) : (
              <Link href={urlBusca(estado, { pagina: numero })}>
                <span className="visualmente-oculto">Página </span>
                {numero}
              </Link>
            )}
          </li>
        ))}
        <li>
          {atual < paginas ? (
            <Link href={urlBusca(estado, { pagina: atual + 1 })} rel="next">
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
