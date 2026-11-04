import { type Resposta, type RespostaRecentes, obterRecentes } from "@/api/cliente";
import { CartaoResultado } from "@/componentes/CartaoResultado";
import { EstadoErro, RecentesVazio } from "@/componentes/Estados";
import { PaginacaoRecentes } from "@/componentes/PaginacaoRecentes";
import { type ParametrosUrl } from "@/lib/busca";
import { lerPaginaRecentes } from "@/lib/recentes";

/**
 * Acórdãos recentes na página inicial (F5-13), renderizados no servidor a partir de
 * ``/?pagina=N``. Página inválida ou além da última vira a página 1, sem erro.
 */
export async function Recentes({ parametros }: { parametros: Promise<ParametrosUrl> }) {
  const pagina = lerPaginaRecentes(await parametros);
  let resposta = await obterRecentes(pagina);
  if (resposta.dados && pagina > 1 && pagina > resposta.dados.total_paginas) {
    resposta = await obterRecentes(1);
  }
  return <ListaRecentes resposta={resposta} />;
}

/** A lista com os estados de vazio e de erro, sem chamar a API (testável no jsdom). */
export function ListaRecentes({ resposta }: { resposta: Resposta<RespostaRecentes> }) {
  if (resposta.falha) return <EstadoErro falha={resposta.falha} assunto="recentes" />;
  const { resultados, pagina, total_paginas } = resposta.dados;
  if (resultados.length === 0) return <RecentesVazio />;
  return (
    <>
      <ol className="lista-resultados">
        {resultados.map((resultado) => (
          <li key={resultado.id}>
            <CartaoResultado resultado={resultado} nivelTitulo={3} />
          </li>
        ))}
      </ol>
      <PaginacaoRecentes pagina={pagina} totalPaginas={total_paginas} />
    </>
  );
}
