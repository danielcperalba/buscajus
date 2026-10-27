"use client";

import { useActionState } from "react";

import type { EstadoPedido } from "@/lib/remocao";

type Acao = (anterior: EstadoPedido, formulario: FormData) => Promise<EstadoPedido>;

type Props = { acao: Acao; referenciaInicial?: string };

/** Formulário de pedido de remoção (F5-11): server action, funciona também sem JavaScript. */
export function FormRemocao({ acao, referenciaInicial = "" }: Props) {
  const [estado, enviar, enviando] = useActionState(acao, {
    situacao: "inicial",
  } satisfies EstadoPedido);

  if (estado.situacao === "enviado") {
    return (
      <div className="estado" role="status">
        <h2>Pedido recebido</h2>
        <p>
          Protocolo nº <strong>{estado.protocolo}</strong>. A resposta será enviada ao e-mail
          informado.
        </p>
      </div>
    );
  }

  const valores = estado.valores ?? { referencia: referenciaInicial, motivo: "", email: "" };
  const erros = estado.situacao === "invalido" ? estado.erros : {};

  function erro(campo: keyof typeof erros) {
    return erros[campo] ? (
      <p id={`erro-${campo}`} className="erro-campo">
        {erros[campo]}
      </p>
    ) : null;
  }

  return (
    <form action={enviar} className="form-remocao" noValidate>
      {estado.situacao === "falhou" ? (
        <p className="estado estado-erro" role="alert">
          {estado.mensagem}
        </p>
      ) : null}
      {estado.situacao === "invalido" ? (
        <p className="erro-campo" role="alert">
          Corrija os campos indicados.
        </p>
      ) : null}
      <div className="campo">
        <label htmlFor="referencia">Número do processo ou link do resultado</label>
        <input
          id="referencia"
          name="referencia"
          required
          maxLength={300}
          defaultValue={valores.referencia}
          aria-invalid={Boolean(erros.referencia)}
          aria-describedby={erros.referencia ? "erro-referencia" : undefined}
        />
        {erro("referencia")}
      </div>
      <div className="campo">
        <label htmlFor="motivo">Motivo</label>
        <textarea
          id="motivo"
          name="motivo"
          required
          minLength={10}
          maxLength={2000}
          rows={5}
          defaultValue={valores.motivo}
          aria-invalid={Boolean(erros.motivo)}
          aria-describedby={erros.motivo ? "erro-motivo" : "ajuda-motivo"}
        />
        <p id="ajuda-motivo" className="ajuda">
          Ex.: o texto traz o meu nome ou dados de uma pessoa envolvida.
        </p>
        {erro("motivo")}
      </div>
      <div className="campo">
        <label htmlFor="email">E-mail para a resposta</label>
        <input
          id="email"
          name="email"
          type="email"
          required
          maxLength={254}
          autoComplete="email"
          defaultValue={valores.email}
          aria-invalid={Boolean(erros.email)}
          aria-describedby={erros.email ? "erro-email" : undefined}
        />
        {erro("email")}
      </div>
      <button type="submit" disabled={enviando}>
        {enviando ? "Enviando…" : "Enviar pedido"}
      </button>
    </form>
  );
}
