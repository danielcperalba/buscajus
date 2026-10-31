import Link from "next/link";

import { FormBusca } from "@/componentes/FormBusca";
import { EXEMPLOS, urlBusca } from "@/lib/busca";

export default function Inicio() {
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
    </div>
  );
}
