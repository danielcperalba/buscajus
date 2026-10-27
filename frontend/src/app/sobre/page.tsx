import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Sobre",
  description: "O que é o BuscaJus, de onde vêm os acórdãos e o que a base cobre.",
};

// F5-10: rascunho, pendente de revisão do conteúdo.
export default function Sobre() {
  return (
    <article className="pagina-texto">
      <h1>Sobre o BuscaJus</h1>
      <p>
        O BuscaJus é uma busca gratuita de jurisprudência por contexto: você descreve a situação
        (por exemplo, &ldquo;disputa por herança familiar&rdquo;) e recebe os acórdãos mais
        relevantes, mesmo que as palavras exatas não apareçam no texto. Cada resultado traz o número
        do processo, a citação pronta para copiar e o link para a fonte oficial.
      </p>

      <h2>Fontes</h2>
      <p>Só fontes oficiais, públicas e gratuitas:</p>
      <ul>
        <li>
          <strong>TJPR</strong>: ementas de acórdãos publicadas no Diário de Justiça Eletrônico
          Nacional (DJEN), do Conselho Nacional de Justiça. O link oficial é a certidão da
          publicação emitida pelo CNJ.
        </li>
        <li>
          <strong>TJDFT</strong>: acórdãos da API pública de jurisprudência do próprio tribunal. O
          link oficial é a página do acórdão no site do TJDFT.
        </li>
      </ul>
      <p>
        O texto exibido é uma reprodução da fonte oficial. Confira sempre o documento original antes
        de citar.
      </p>

      <h2>Cobertura</h2>
      <ul>
        <li>TJPR: ementas publicadas no DJEN a partir de 23/07/2025.</li>
        <li>TJDFT: acórdãos publicados a partir do início da coleta.</li>
      </ul>
      <p>
        Acórdãos do TJDFT sob segredo de justiça não entram na base. A cobertura exata por tribunal
        e período passará a ser mostrada aqui a partir dos dados da própria base.
      </p>

      <h2>Privacidade e remoção</h2>
      <p>
        Nomes de pessoas nas ementas são trocados por iniciais antes de qualquer gravação. Veja a{" "}
        <Link href="/privacidade">política de privacidade</Link> e, se encontrar dado pessoal,{" "}
        <Link href="/remocao">solicite a remoção</Link>.
      </p>
    </article>
  );
}
