// IP do usuário a repassar para a API (segurança do limite de taxa por IP).

const IPV4 = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/;
const IPV6 = /^[0-9a-f:.]+$/i;

function ipValido(valor: string): boolean {
  const v4 = IPV4.exec(valor);
  if (v4) return v4.slice(1).every((parte) => Number(parte) <= 255);
  return valor.includes(":") && IPV6.test(valor);
}

/**
 * Último item do X-Forwarded-For recebido: o acrescentado pelo proxy reverso. Nunca a lista
 * inteira (os itens anteriores vêm do cliente). Ausente ou malformado → `undefined`.
 */
export function ipAcrescentadoPeloProxy(cabecalho: string | null | undefined): string | undefined {
  if (!cabecalho) return undefined;
  const ultimo = cabecalho.split(",").at(-1)?.trim() ?? "";
  return ipValido(ultimo) ? ultimo : undefined;
}
