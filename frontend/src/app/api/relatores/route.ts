// Sugestões de relator para o filtro (F5-06). Ponte para a API: o navegador só fala com o
// próprio site, e o limite de taxa da API vale pelo IP do usuário (cliente.ts).
import type { NextRequest } from "next/server";

import { sugerirRelatores } from "@/api/cliente";

export async function GET(request: NextRequest) {
  const prefixo = request.nextUrl.searchParams.get("prefixo")?.trim() ?? "";
  if (prefixo.length < 2 || prefixo.length > 100) {
    return Response.json([]);
  }
  const resposta = await sugerirRelatores(prefixo);
  if (resposta.falha) {
    return Response.json([], { status: resposta.falha.status === 429 ? 429 : 502 });
  }
  return Response.json(resposta.dados);
}
