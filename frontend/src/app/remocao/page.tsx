import type { Metadata } from "next";
import { Suspense } from "react";

import { FormRemocao } from "@/componentes/FormRemocao";

import { enviarPedido } from "./acoes";

export const metadata: Metadata = { title: "Solicitar remoção" };

/** Canal de remoção (F5-11; ARCHITECTURE.md, seção 6.5). */
export default function Remocao({ searchParams }: PageProps<"/remocao">) {
  return (
    <article className="pagina-texto">
      <h1>Solicitar remoção</h1>
      <p>
        Se um acórdão exibido aqui traz dado pessoal seu (ou de alguém que você representa), peça a
        remoção. Cada pedido é analisado por uma pessoa; aceito, o texto sai da busca e é apagado da
        nossa base, e a coleta não volta a incluí-lo.
      </p>
      <p>
        O e-mail informado é usado só para responder ao pedido e é apagado 90 dias depois da
        resposta.
      </p>
      <Suspense fallback={<FormRemocao acao={enviarPedido} />}>
        <FormularioComReferencia parametros={searchParams} />
      </Suspense>
      <Contato />
    </article>
  );
}

async function FormularioComReferencia({
  parametros,
}: {
  parametros: Promise<Record<string, string | string[] | undefined>>;
}) {
  const bruta = (await parametros).referencia;
  const referencia = (Array.isArray(bruta) ? bruta[0] : bruta)?.slice(0, 300) ?? "";
  return <FormRemocao acao={enviarPedido} referenciaInicial={referencia} />;
}

/** E-mail de contato como texto (não como link de formulário), se configurado. */
function Contato() {
  const email = process.env.CONTATO_EMAIL;
  if (!email) return null;
  return (
    <p>
      Também é possível escrever para <span className="contato">{email}</span>.
    </p>
  );
}
