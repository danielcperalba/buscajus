import Link from "next/link";

import type { FalhaApi } from "@/api/cliente";
import { EXEMPLOS, LIMITE_RESULTADOS, urlBusca } from "@/lib/busca";

/** Esqueleto enquanto a busca carrega (F5-07). */
export function Carregando() {
  return (
    <div className="carregando" role="status" aria-live="polite">
      <span className="visualmente-oculto">Buscando acórdãos…</span>
      {[0, 1, 2].map((i) => (
        <div key={i} className="cartao cartao-esqueleto" aria-hidden="true" />
      ))}
    </div>
  );
}

/** Nenhum resultado: sugestões para reformular (F5-07). */
export function EstadoVazio({ filtrando }: { filtrando: boolean }) {
  return (
    <section className="estado" aria-labelledby="titulo-vazio">
      <h2 id="titulo-vazio">Nenhum acórdão encontrado</h2>
      <ul>
        <li>Descreva a situação com outras palavras, sem termos muito específicos.</li>
        {filtrando ? <li>Tire alguns filtros: eles valem todos ao mesmo tempo.</li> : null}
        <li>Confira o número do processo, se buscou por um.</li>
      </ul>
      <p>Exemplos de busca:</p>
      <ul className="exemplos">
        {EXEMPLOS.map((exemplo) => (
          <li key={exemplo}>
            <Link href={urlBusca({ q: exemplo, pagina: 1 })}>{exemplo}</Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

function mensagemDeErro(falha: FalhaApi): string {
  if (falha.status === 429) {
    return "Muitas buscas em pouco tempo. Aguarde um minuto e tente de novo.";
  }
  if (falha.status === 422) {
    return `A busca não pôde ser feita: ${falha.mensagem}.`;
  }
  return "A busca está indisponível no momento. Tente de novo em alguns minutos.";
}

/** Falha da API (F5-07). */
export function EstadoErro({ falha }: { falha: FalhaApi }) {
  return (
    <section className="estado estado-erro" role="alert" aria-labelledby="titulo-erro">
      <h2 id="titulo-erro">Não foi possível buscar</h2>
      <p>{mensagemDeErro(falha)}</p>
    </section>
  );
}

/** Aviso de que só os mais relevantes são mostrados (F5-07). */
export function AvisoLimite({ total }: { total: number }) {
  if (total < LIMITE_RESULTADOS) return null;
  return (
    <p className="aviso-limite">
      Mostrando os {LIMITE_RESULTADOS} acórdãos mais relevantes. Para ver outros, refine a busca ou
      use os filtros.
    </p>
  );
}
