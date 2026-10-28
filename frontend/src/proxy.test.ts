// @vitest-environment node
import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { proxy } from "./proxy";

type Rota = (url: string, init?: RequestInit) => Promise<Response>;

const PAGINAS: Record<string, string> = {
  "/nao-encontrado": "<h1>Acórdão não encontrado</h1>",
  "/indisponivel": "<h1>Serviço temporariamente indisponível</h1>",
  "/acordao/4": "<h1>Acórdão removido</h1>",
};

/** fetch simulado: a API de situação responde por ``api``; as páginas locais, por PAGINAS. */
function simular(api: Rota) {
  const chamadas: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      chamadas.push(url);
      if (url.includes("/api/v1/acordaos/")) return api(url, init);
      const caminho = new URL(url).pathname;
      return new Response(PAGINAS[caminho] ?? "?", { headers: { "content-type": "text/html" } });
    }),
  );
  return chamadas;
}

function pedido(caminho: string, cabecalhos: Record<string, string> = {}) {
  return new NextRequest(new URL(caminho, "https://buscajus.exemplo"), { headers: cabecalhos });
}

function json(corpo: unknown, status = 200) {
  return new Response(JSON.stringify(corpo), { status });
}

beforeEach(() => {
  vi.stubEnv("API_URL", "http://api:8000");
  vi.stubEnv("API_TIMEOUT_SITUACAO_MS", "50");
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("proxy do detalhe do acórdão", () => {
  it("ativo segue para a página", async () => {
    simular(async () => json({ situacao: "ativo" }));
    const resposta = await proxy(pedido("/acordao/2"));
    expect(resposta.headers.get("x-middleware-next")).toBe("1");
  });

  it("inexistente e id inválido → 404 com a página de não encontrado", async () => {
    simular(async () => json({ erro: "nao_encontrado" }, 404));
    const resposta = await proxy(pedido("/acordao/99"));
    expect(resposta.status).toBe(404);
    expect(await resposta.text()).toContain("Acórdão não encontrado");
    expect((await proxy(pedido("/acordao/abc"))).status).toBe(404);
  });

  it("removido → 410 com a própria página de aviso", async () => {
    simular(async () => json({ situacao: "removido" }));
    const resposta = await proxy(pedido("/acordao/4"));
    expect(resposta.status).toBe(410);
    expect(await resposta.text()).toContain("Acórdão removido");
  });

  it.each([
    [
      "fora do ar",
      async () => Promise.reject(new TypeError("fetch failed: ECONNREFUSED api:8000")),
    ],
    ["com erro 500", async () => json({ detail: "Traceback (most recent call last)" }, 500)],
    ["com corpo inesperado", async () => new Response("<html>gateway</html>")],
    ["com situação desconhecida", async () => json({ situacao: "quarentena" })],
  ] as [string, Rota][])("API %s → 503 sem detalhes", async (_caso, api) => {
    simular(api);
    const resposta = await proxy(pedido("/acordao/2"));
    expect(resposta.status).toBe(503);
    expect(resposta.headers.get("retry-after")).toBe("30");
    expect(resposta.headers.get("cache-control")).toBe("no-store");
    const corpo = await resposta.text();
    expect(corpo).toContain("Serviço temporariamente indisponível");
    for (const detalhe of ["ECONNREFUSED", "Traceback", "api:8000", "gateway"]) {
      expect(corpo).not.toContain(detalhe);
    }
  });

  it("API lenta: desiste no timeout e responde 503 sem travar", async () => {
    simular(
      (_url, init) =>
        new Promise((_resolver, rejeitar) => {
          // Nunca responde; só termina quando o sinal de timeout aborta.
          init?.signal?.addEventListener("abort", () => rejeitar(init.signal?.reason));
        }),
    );
    const inicio = Date.now();
    const resposta = await proxy(pedido("/acordao/2"));
    expect(resposta.status).toBe(503);
    expect(Date.now() - inicio).toBeLessThan(2000);
  });

  it("se nem a página local responde, texto simples com o mesmo status", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url.includes("/api/v1/")) throw new TypeError("fetch failed");
        throw new TypeError("local fora do ar");
      }),
    );
    const resposta = await proxy(pedido("/acordao/2"));
    expect(resposta.status).toBe(503);
    expect(await resposta.text()).toBe(
      "Serviço temporariamente indisponível. Tente de novo em instantes.",
    );
  });

  it("navegação interna (RSC), outros métodos e pedidos do próprio proxy não são conferidos", async () => {
    const chamadas = simular(async () => json({}, 404));
    for (const req of [
      pedido("/acordao/99", { rsc: "1" }),
      pedido("/acordao/99", { "x-buscajus-situacao-conferida": "1" }),
      new NextRequest(new URL("/acordao/99", "https://buscajus.exemplo"), { method: "POST" }),
    ]) {
      expect((await proxy(req)).headers.get("x-middleware-next")).toBe("1");
    }
    expect(chamadas).toEqual([]);
  });
});
