import Link from "next/link";
import { Suspense } from "react";

import { Carregando } from "@/componentes/Estados";
import { FormBusca } from "@/componentes/FormBusca";
import { Recentes } from "@/componentes/Recentes";
import { EXEMPLOS, urlBusca } from "@/lib/busca";
import { ANCORA_RECENTES } from "@/lib/recentes";

/**
 * Página inicial. Formulário e exemplos são estáticos; a lista de acórdãos recentes (F5-13) lê
 * ``?pagina=`` e fica num Suspense (exigência do Cache Components), em streaming do servidor.
 */
export default function Inicio({ searchParams }: PageProps<"/">) {
  return (
    <div className="inicio">
      <h1>Jurisprudência por contexto</h1>
      <p className="subtitulo">
        Descreva a situação e encontre acórdãos relevantes, com o número do processo e a citação
        pronta. Os textos vêm de fontes oficiais.
      </p>
      <FormBusca destaque />
      <section aria-labelledby="titulo-exemplos" className="exemplos-inicio">
        <h2 id="titulo-exemplos">Exemplos</h2>
        <ul className="exemplos">
          {EXEMPLOS.map((exemplo) => (
            <li key={exemplo}>
              <Link href={urlBusca({ q: exemplo, pagina: 1 })}>{exemplo}</Link>
            </li>
          ))}
        </ul>
      </section>
      <section id={ANCORA_RECENTES} aria-labelledby="titulo-recentes" className="recentes">
        <h2 id="titulo-recentes">Acórdãos recentes</h2>
        <Suspense fallback={<Carregando mensagem="Carregando acórdãos recentes…" />}>
          <Recentes parametros={searchParams} />
        </Suspense>
      </section>
    </div>
  );
}
