"use server";

import { registrarRemocao } from "@/api/cliente";
import type { EstadoPedido } from "@/lib/remocao";
import { validarPedido } from "@/lib/remocao";

/** Envia o pedido de remoção à API (F5-11). Roda no servidor; o navegador não fala com a API. */
export async function enviarPedido(
  _anterior: EstadoPedido,
  formulario: FormData,
): Promise<EstadoPedido> {
  const valores = {
    referencia: String(formulario.get("referencia") ?? "").trim(),
    motivo: String(formulario.get("motivo") ?? "").trim(),
    email: String(formulario.get("email") ?? "").trim(),
  };
  const erros = validarPedido(valores);
  if (Object.keys(erros).length > 0) {
    return { situacao: "invalido", valores, erros };
  }
  const resposta = await registrarRemocao(valores);
  if (resposta.dados) {
    return { situacao: "enviado", protocolo: resposta.dados.protocolo };
  }
  if (resposta.falha.erro === "referencia_invalida") {
    return {
      situacao: "invalido",
      valores,
      erros: { referencia: "Informe o número completo do processo ou o link do resultado." },
    };
  }
  return {
    situacao: "falhou",
    valores,
    mensagem:
      resposta.falha.status === 429
        ? "Muitos pedidos em pouco tempo. Tente de novo mais tarde."
        : "Não foi possível registrar o pedido agora. Tente de novo em alguns minutos.",
  };
}
