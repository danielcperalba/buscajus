import Link from "next/link";

import type { ResultadoBusca } from "@/api/cliente";
import { CopiarCitacao } from "@/componentes/CopiarCitacao";
import { formatarData, trechoSeguro } from "@/lib/busca";

type Props = { resultado: ResultadoBusca };

function relatorExibido(resultado: ResultadoBusca): string | undefined {
  if (resultado.relator_designado) {
    return `${resultado.relator_designado} (relator para o acórdão)`;
  }
  return resultado.relator ?? undefined;
}

/** Cartão de um acórdão na lista de resultados (F5-04). */
export function CartaoResultado({ resultado }: Props) {
  const datas = [
    ["Julgado em", formatarData(resultado.data_julgamento)],
    ["Publicado em", formatarData(resultado.data_publicacao)],
    ["Disponibilizado no DJEN em", formatarData(resultado.data_disponibilizacao)],
  ].filter((par): par is [string, string] => par[1] !== undefined);
  const metadados = [
    ["Tribunal", resultado.tribunal],
    ["Órgão julgador", resultado.orgao_julgador],
    ["Classe", resultado.classe.nome],
    ["Relator", relatorExibido(resultado)],
    ...datas,
  ].filter((par): par is [string, string] => Boolean(par[1]));
  const tituloId = `resultado-${resultado.id}`;

  return (
    <article className="cartao" aria-labelledby={tituloId}>
      <h2 id={tituloId} className="cartao-numero">
        <Link href={`/acordao/${resultado.id}`}>{resultado.numero_processo}</Link>
      </h2>
      <dl className="cartao-metadados">
        {metadados.map(([rotulo, valor]) => (
          <div key={rotulo}>
            <dt>{rotulo}</dt>
            <dd>{valor}</dd>
          </div>
        ))}
      </dl>
      <p
        className="cartao-trecho"
        // O trecho só pode conter <mark>: escapado na API e de novo em trechoSeguro.
        dangerouslySetInnerHTML={{ __html: trechoSeguro(resultado.trecho) }}
      />
      <div className="cartao-acoes">
        <CopiarCitacao citacao={resultado.citacao} />
        <a href={resultado.link_oficial} target="_blank" rel="noopener noreferrer">
          Ver na fonte oficial<span className="visualmente-oculto"> (abre em nova aba)</span>
        </a>
        {resultado.link_tribunal ? (
          <a
            className="link-secundario"
            href={resultado.link_tribunal}
            target="_blank"
            rel="noopener noreferrer"
          >
            Ver no sistema do tribunal
            <span className="visualmente-oculto"> (abre em nova aba)</span>
          </a>
        ) : null}
      </div>
      <p className="aviso">{resultado.aviso}</p>
    </article>
  );
}
