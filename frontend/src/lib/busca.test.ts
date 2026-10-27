import { describe, expect, it } from "vitest";

import {
  consultaApi,
  filtrosAtivos,
  formatarData,
  lerEstado,
  trechoSeguro,
  urlBusca,
} from "./busca";

describe("estado da busca na URL", () => {
  it("lê consulta, filtros e página, descartando valores inválidos", () => {
    const estado = lerEstado({
      q: "  herança  ",
      tribunal: "TJDFT",
      classe: "abc",
      data_inicio: "2026-10-01",
      data_fim: "01/10/2026",
      relator: ["Fulano", "Outro"],
      pagina: "3",
      orgao: "",
    });
    expect(estado).toEqual({
      q: "herança",
      tribunal: "TJDFT",
      data_inicio: "2026-10-01",
      relator: "Fulano",
      pagina: 3,
    });
    expect(lerEstado({ pagina: "11" }).pagina).toBe(1);
    expect(lerEstado({ pagina: "0" }).pagina).toBe(1);
    expect(lerEstado({}).q).toBe("");
  });

  it("monta a consulta da API", () => {
    const estado = lerEstado({ q: "x", classe: "198", pagina: "2" });
    expect(consultaApi(estado)).toMatchObject({ q: "x", classe: 198, pagina: 2 });
  });

  it("monta a URL preservando os filtros e omitindo a página 1", () => {
    const estado = lerEstado({ q: "dano moral", tribunal: "TJPR", pagina: "2" });
    expect(urlBusca(estado)).toBe("/busca?q=dano+moral&tribunal=TJPR&pagina=2");
    expect(urlBusca(estado, { pagina: 1 })).toBe("/busca?q=dano+moral&tribunal=TJPR");
    expect(urlBusca(estado, { tribunal: undefined, pagina: 4 })).toBe(
      "/busca?q=dano+moral&pagina=4",
    );
    expect(filtrosAtivos(estado)).toEqual(["tribunal"]);
  });
});

describe("exibição", () => {
  it("deixa passar só <mark> no trecho", () => {
    expect(trechoSeguro("a <mark>b</mark> &lt;c&gt;")).toBe("a <mark>b</mark> &lt;c&gt;");
    expect(trechoSeguro('<img src=x onerror="alert(1)"><mark>b</mark>')).toBe(
      '&lt;img src=x onerror="alert(1)"><mark>b</mark>',
    );
    expect(trechoSeguro("<marker>")).toBe("&lt;marker>");
  });

  it("formata datas ISO", () => {
    expect(formatarData("2026-10-08")).toBe("08/10/2026");
    expect(formatarData(null)).toBeUndefined();
    expect(formatarData("ontem")).toBeUndefined();
  });
});
