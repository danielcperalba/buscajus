import Link from "next/link";

import type { DetalheAcordao, Indisponivel } from "@/api/cliente";
import { CopiarCitacao } from "@/componentes/CopiarCitacao";
import { formatarData } from "@/lib/busca";

function metadados(acordao: DetalheAcordao): [string, string][] {
  const pares: [string, string | null | undefined][] = [
    ["Tribunal", acordao.tribunal],
    ["Órgão julgador", acordao.orgao_julgador],
    ["Classe", acordao.classe.nome],
    ["Relator", acordao.relator],
    ["Relator para o acórdão", acordao.relator_designado],
    ["Julgado em", formatarData(acordao.data_julgamento)],
    ["Publicado em", formatarData(acordao.data_publicacao)],
    ["Disponibilizado no DJEN em", formatarData(acordao.data_disponibilizacao)],
    ["Turma recursal", acordao.turma_recursal ? "Sim" : undefined],
  ];
  return pares.filter((par): par is [string, string] => Boolean(par[1]));
}

/** Página de detalhe de um acórdão (F5-08). */
export function Detalhe({ acordao }: { acordao: DetalheAcordao }) {
  const remocao = `/remocao?referencia=${encodeURIComponent(`/acordao/${acordao.id}`)}`;
  return (
    <article className="detalhe">
      <p className="detalhe-rotulo">Acórdão · {acordao.tribunal}</p>
      <h1>{acordao.numero_processo}</h1>
      <dl className="cartao-metadados detalhe-metadados">
        {metadados(acordao).map(([rotulo, valor]) => (
          <div key={rotulo}>
            <dt>{rotulo}</dt>
            <dd>{valor}</dd>
          </div>
        ))}
      </dl>

      <section aria-labelledby="titulo-ementa">
        <h2 id="titulo-ementa">Ementa</h2>
        <p className="texto-integral">{acordao.ementa}</p>
      </section>

      {acordao.decisao ? (
        <section aria-labelledby="titulo-decisao">
          <h2 id="titulo-decisao">Dispositivo</h2>
          <p className="texto-integral">{acordao.decisao}</p>
        </section>
      ) : null}

      <section aria-labelledby="titulo-citacao">
        <h2 id="titulo-citacao">Citação</h2>
        <p className="citacao">{acordao.citacao}</p>
        <CopiarCitacao citacao={acordao.citacao} />
      </section>

      <section aria-labelledby="titulo-fontes">
        <h2 id="titulo-fontes">Fonte oficial</h2>
        <ul className="links-oficiais">
          <li>
            <a href={acordao.link_oficial} target="_blank" rel="noopener noreferrer">
              Ver na fonte oficial
              <span className="visualmente-oculto"> (abre em nova aba)</span>
            </a>
          </li>
          {acordao.link_tribunal ? (
            <li>
              <a href={acordao.link_tribunal} target="_blank" rel="noopener noreferrer">
                Ver no sistema do tribunal
                <span className="visualmente-oculto"> (abre em nova aba)</span>
              </a>
            </li>
          ) : null}
          <li>
            <Link href={`/processo/${encodeURIComponent(acordao.numero_processo)}`}>
              Outros acórdãos deste processo
            </Link>
          </li>
        </ul>
        <p className="aviso">{acordao.aviso}</p>
      </section>

      <p className="solicitar-remocao">
        Há dado pessoal neste texto? <Link href={remocao}>Solicitar remoção</Link>
      </p>
    </article>
  );
}

/** Acórdão cancelado na fonte ou removido (HTTP 410 da API). */
export function AcordaoIndisponivel({ indisponivel }: { indisponivel: Indisponivel }) {
  return (
    <section className="estado" aria-labelledby="titulo-indisponivel">
      <h1 id="titulo-indisponivel">
        {indisponivel.erro === "cancelado" ? "Publicação cancelada" : "Acórdão removido"}
      </h1>
      <p>{indisponivel.mensagem}</p>
      {indisponivel.link_oficial ? (
        <p>
          <a href={indisponivel.link_oficial} target="_blank" rel="noopener noreferrer">
            Consultar a fonte oficial
            <span className="visualmente-oculto"> (abre em nova aba)</span>
          </a>
        </p>
      ) : null}
      <p>
        <Link href="/busca">Voltar para a busca</Link>
      </p>
    </section>
  );
}
