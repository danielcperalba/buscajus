import type { Metadata } from "next";
import { Suspense } from "react";

import { obterProcesso } from "@/api/cliente";
import { CartaoResultado } from "@/componentes/CartaoResultado";
import { Carregando, EstadoErro } from "@/componentes/Estados";

export async function generateMetadata({
  params,
}: PageProps<"/processo/[numero]">): Promise<Metadata> {
  const { numero } = await params;
  return { title: `Processo ${numero}` };
}

/** Acórdãos de um processo (F5-09): número com ou sem máscara. */
export default function PaginaProcesso({ params }: PageProps<"/processo/[numero]">) {
  return (
    <Suspense fallback={<Carregando />}>
      <Conteudo parametros={params} />
    </Suspense>
  );
}

async function Conteudo({ parametros }: { parametros: Promise<{ numero: string }> }) {
  const { numero } = await parametros;
  const resposta = await obterProcesso(numero);
  if (resposta.falha) {
    if (resposta.falha.status === 404 || resposta.falha.status === 422) {
      return (
        <section className="estado" aria-labelledby="titulo-processo">
          <h1 id="titulo-processo">Processo {numero}</h1>
          <p>
            {resposta.falha.status === 404
              ? "Nenhum acórdão deste processo está na base."
              : "Número de processo inválido. Use o número CNJ, com ou sem máscara."}
          </p>
        </section>
      );
    }
    return <EstadoErro falha={resposta.falha} />;
  }
  const { numero_processo, acordaos } = resposta.dados;
  return (
    <section aria-labelledby="titulo-processo">
      <h1 id="titulo-processo">Processo {numero_processo}</h1>
      <p className="resumo">{acordaos.length} acórdão(s), do mais recente ao mais antigo.</p>
      <ol className="lista-resultados">
        {acordaos.map((acordao) => (
          <li key={acordao.id}>
            <CartaoResultado resultado={acordao} />
          </li>
        ))}
      </ol>
    </section>
  );
}
