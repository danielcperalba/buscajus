import Form from "next/form";
import type { ReactNode } from "react";

type Props = { consulta?: string; children?: ReactNode; destaque?: boolean };

/**
 * Formulário GET para /busca (F5-03): a URL é o estado da busca. Funciona sem JavaScript;
 * com ele, o ``next/form`` navega sem recarregar a página. Enviar volta para a página 1.
 */
export function FormBusca({ consulta = "", children, destaque = false }: Props) {
  return (
    <Form action="/busca" className={destaque ? "form-busca form-busca-destaque" : "form-busca"}>
      <div className="campo-busca">
        <label htmlFor="q">Descreva a situação ou informe o número do processo</label>
        <div className="campo-busca-linha">
          <input
            id="q"
            name="q"
            type="search"
            required
            maxLength={500}
            defaultValue={consulta}
            placeholder="Ex.: disputa por herança familiar"
            autoComplete="off"
          />
          <button type="submit">Buscar</button>
        </div>
      </div>
      {children}
    </Form>
  );
}
