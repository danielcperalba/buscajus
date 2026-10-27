// Validação do pedido de remoção (F5-11), espelhando os limites da API (PedidoRemocao).

export type ValoresPedido = { referencia: string; motivo: string; email: string };
export type ErrosPedido = Partial<Record<keyof ValoresPedido, string>>;

export type EstadoPedido =
  | { situacao: "inicial"; valores?: ValoresPedido }
  | { situacao: "invalido"; valores: ValoresPedido; erros: ErrosPedido }
  | { situacao: "falhou"; valores: ValoresPedido; mensagem: string }
  | { situacao: "enviado"; protocolo: number };

const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

export function validarPedido(valores: ValoresPedido): ErrosPedido {
  const erros: ErrosPedido = {};
  if (valores.referencia.length < 5 || valores.referencia.length > 300) {
    erros.referencia = "Informe o número do processo ou o link do resultado.";
  }
  if (valores.motivo.length < 10 || valores.motivo.length > 2000) {
    erros.motivo = "Explique o motivo em pelo menos 10 caracteres (até 2.000).";
  }
  if (!EMAIL.test(valores.email) || valores.email.length > 254) {
    erros.email = "Informe um e-mail válido para a resposta.";
  }
  return erros;
}
