import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Privacidade",
  description: "Quais dados o BuscaJus trata, por quê, e como pedir a remoção de um acórdão.",
};

// F5-10: rascunho, pendente de revisão jurídica (em especial a base legal).
export default function Privacidade() {
  return (
    <article className="pagina-texto">
      <h1>Privacidade</h1>

      <h2>Quais dados tratamos</h2>
      <ul>
        <li>
          <strong>Acórdãos</strong>: número do processo, tribunal, órgão julgador, classe, relator,
          datas, ementa, dispositivo (TJDFT) e links oficiais, como publicados nas fontes oficiais.
          Não guardamos partes, advogados nem destinatários das publicações.
        </li>
        <li>
          <strong>Nomes no texto</strong>: antes de qualquer gravação, nomes de pessoas nas ementas
          são trocados por iniciais e números de CPF são mascarados. Se a verificação automática
          encontra um dado pessoal remanescente, o acórdão fica fora da busca até uma revisão
          manual.
        </li>
        <li>
          <strong>Segredo de justiça</strong>: acórdãos do TJDFT sob segredo de justiça não são
          coletados. Se um acórdão já exibido passa a ficar sob segredo, ele é removido e seu texto
          é apagado da base.
        </li>
        <li>
          <strong>Buscas</strong>: não guardamos o que você digita nem associamos buscas a pessoas.
          Os registros de funcionamento do serviço não contêm os termos de busca.
        </li>
        <li>
          <strong>Pedidos de remoção</strong>: guardamos o pedido e o e-mail informado, usado só
          para responder. O e-mail é apagado 90 dias depois da resposta.
        </li>
      </ul>

      <h2>Finalidade e base legal</h2>
      <p>
        A finalidade é exclusivamente a pesquisa de jurisprudência. Os acórdãos são documentos
        públicos, publicados oficialmente pelos tribunais e pelo CNJ; o tratamento segue a Lei Geral
        de Proteção de Dados (Lei 13.709/2018), em especial as regras para dados tornados públicos
        (art. 7º, §§ 3º e 4º), com a minimização descrita acima. Não há busca por nome de parte e
        não cruzamos números de processo com outras fontes.
      </p>

      <h2>Sem rastreadores</h2>
      <p>O site não usa cookies de publicidade nem ferramentas de rastreamento de terceiros.</p>

      <h2>Remoção</h2>
      <p>
        Se um acórdão traz dado pessoal seu, <Link href="/remocao">solicite a remoção</Link>. Aceito
        o pedido, o acórdão sai da busca, o texto é apagado da nossa base e a coleta não volta a
        incluí-lo.
      </p>
    </article>
  );
}
