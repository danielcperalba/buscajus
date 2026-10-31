import type { Metadata } from "next";
import { Suspense } from "react";

import { buscar, obterFiltros } from "@/api/cliente";
import { CartaoResultado } from "@/componentes/CartaoResultado";
import { AvisoLimite, Carregando, EstadoErro, EstadoVazio } from "@/componentes/Estados";
import { Filtros } from "@/componentes/Filtros";
import { FormBusca } from "@/componentes/FormBusca";
import { Paginacao } from "@/componentes/Paginacao";
import { type ParametrosUrl, consultaApi, filtrosAtivos, lerEstado } from "@/lib/busca";

export const metadata: Metadata = {
  title: "Busca",
  // A consulta não vai para o título nem para buscadores.
  robots: { index: false },
};

/**
 * Página de busca (F5-03): o estado vem da URL. Os parâmetros são dados de execução, então
 * tudo o que depende deles fica dentro do Suspense (exigência do Cache Components).
 */
export default function PaginaBusca({ searchParams }: PageProps<"/busca">) {
  return (
    <div className="pagina-busca">
      <h1 className="visualmente-oculto">Busca de acórdãos</h1>
      <Suspense
        fallback={
          <>
            <FormBusca />
            <Carregando />
          </>
        }
      >
        <Busca parametros={searchParams} />
      </Suspense>
    </div>
  );
}

async function Busca({ parametros }: { parametros: Promise<ParametrosUrl> }) {
  const estado = lerEstado(await parametros);
  const [opcoes, resposta] = await Promise.all([
    obterFiltros(),
    estado.q ? buscar(consultaApi(estado)) : Promise.resolve(undefined),
  ]);
  return (
    <>
      <FormBusca consulta={estado.q}>
        <Filtros opcoes={opcoes.dados} estado={estado} />
      </FormBusca>
      <section aria-labelledby="titulo-resultados" className="resultados">
        <h2 id="titulo-resultados" className="visualmente-oculto">
          Resultados
        </h2>
        {resposta === undefined ? (
          <p>Descreva a situação acima para ver acórdãos relevantes.</p>
        ) : resposta.falha ? (
          <EstadoErro falha={resposta.falha} />
        ) : resposta.dados.total === 0 ? (
          <EstadoVazio filtrando={filtrosAtivos(estado).length > 0} />
        ) : (
          <>
            <p className="resumo" role="status">
              {resposta.dados.tipo === "processo"
                ? `${resposta.dados.total} acórdão(s) do processo ${resposta.dados.numero_processo}`
                : `${resposta.dados.total} acórdão(s) encontrado(s)`}
            </p>
            <AvisoLimite total={resposta.dados.total} />
            <ol className="lista-resultados">
              {resposta.dados.resultados.map((resultado) => (
                <li key={resultado.id}>
                  <CartaoResultado resultado={resultado} />
                </li>
              ))}
            </ol>
            <Paginacao estado={estado} total={resposta.dados.total} />
          </>
        )}
      </section>
    </>
  );
}
