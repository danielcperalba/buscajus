import Link from "next/link";

import type { FalhaApi } from "@/api/cliente";
import { EXEMPLOS, LIMITE_RESULTADOS, urlBusca } from "@/lib/busca";

/** Esqueleto enquanto a busca (ou a lista de recentes) carrega (F5-07). */
export function Carregando({ mensagem = "Buscando acórdãos…" }: { mensagem?: string }) {
  return (
    <div className="carregando" role="status" aria-live="polite">
      <span className="visualmente-oculto">{mensagem}</span>
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

/** Lista de acórdãos recentes vazia: a base ainda não tem acórdãos exibíveis (F5-13). */
export function RecentesVazio() {
  return (
    <section className="estado" aria-labelledby="titulo-recentes-vazio">
      <h3 id="titulo-recentes-vazio">Nenhum acórdão disponível ainda</h3>
      <p>Os acórdãos aparecem aqui assim que forem coletados das fontes oficiais.</p>
    </section>
  );
}

type Assunto = "busca" | "recentes";

function mensagemDeErro(falha: FalhaApi, assunto: Assunto): string {
  if (falha.status === 429) {
    return assunto === "busca"
      ? "Muitas buscas em pouco tempo. Aguarde um minuto e tente de novo."
      : "Muitas consultas em pouco tempo. Aguarde um minuto e recarregue a página.";
  }
  if (falha.status === 422 && assunto === "busca") {
    return `A busca não pôde ser feita: ${falha.mensagem}.`;
  }
  return assunto === "busca"
    ? "A busca está indisponível no momento. Tente de novo em alguns minutos."
    : "A lista está indisponível no momento. Tente de novo em alguns minutos.";
}

/**
 * Falha da API (F5-07). Na lista de recentes (F5-13), o título é h3, porque fica dentro da
 * seção com título h2.
 */
export function EstadoErro({ falha, assunto = "busca" }: { falha: FalhaApi; assunto?: Assunto }) {
  const Titulo = assunto === "busca" ? "h2" : "h3";
  const tituloId = assunto === "busca" ? "titulo-erro" : "titulo-erro-recentes";
  return (
    <section className="estado estado-erro" role="alert" aria-labelledby={tituloId}>
      <Titulo id={tituloId}>
        {assunto === "busca"
          ? "Não foi possível buscar"
          : "Não foi possível carregar os acórdãos recentes"}
      </Titulo>
      <p>{mensagemDeErro(falha, assunto)}</p>
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
