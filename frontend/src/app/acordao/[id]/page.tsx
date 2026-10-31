import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import { obterDetalhe } from "@/api/cliente";
import { AcordaoIndisponivel, Detalhe } from "@/componentes/Detalhe";
import { Carregando, EstadoErro } from "@/componentes/Estados";

function idValido(bruto: string): number | undefined {
  return /^\d{1,18}$/.test(bruto) ? Number(bruto) : undefined;
}

export async function generateMetadata({ params }: PageProps<"/acordao/[id]">): Promise<Metadata> {
  const id = idValido((await params).id);
  const resposta = id === undefined ? undefined : await obterDetalhe(id);
  if (!resposta?.dados) {
    return { title: "Acórdão", robots: { index: false } };
  }
  const { tribunal, numero_processo, classe } = resposta.dados;
  return {
    title: `${classe.nome ?? "Acórdão"} ${numero_processo} (${tribunal})`,
    description: `Ementa, citação e link para a fonte oficial do acórdão no processo ${numero_processo}.`,
  };
}

/** Detalhe do acórdão (F5-08), renderizado no servidor. */
export default function PaginaAcordao({ params }: PageProps<"/acordao/[id]">) {
  return (
    <Suspense fallback={<Carregando />}>
      <Conteudo parametros={params} />
    </Suspense>
  );
}

async function Conteudo({ parametros }: { parametros: Promise<{ id: string }> }) {
  const id = idValido((await parametros).id);
  if (id === undefined) notFound();
  const resposta = await obterDetalhe(id);
  if (resposta.dados) return <Detalhe acordao={resposta.dados} />;
  if (resposta.indisponivel) return <AcordaoIndisponivel indisponivel={resposta.indisponivel} />;
  if (resposta.falha.status === 404) notFound();
  return <EstadoErro falha={resposta.falha} />;
}
