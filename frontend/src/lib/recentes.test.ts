import { describe, expect, it } from "vitest";

import { lerPaginaRecentes, urlRecentes } from "./recentes";

describe("página dos acórdãos recentes na URL (F5-13)", () => {
  it("lê páginas de 1 a 100", () => {
    expect(lerPaginaRecentes({})).toBe(1);
    expect(lerPaginaRecentes({ pagina: "2" })).toBe(2);
    expect(lerPaginaRecentes({ pagina: " 100 " })).toBe(100);
    expect(lerPaginaRecentes({ pagina: ["3", "4"] })).toBe(3);
  });

  it.each(["0", "-1", "101", "1e2", "2.5", "abc", "", "0x2"])(
    "%j inválida ou fora do limite vira a página 1",
    (pagina) => {
      expect(lerPaginaRecentes({ pagina })).toBe(1);
    },
  );

  it("URL sem parâmetro na primeira página e com a âncora da seção", () => {
    expect(urlRecentes(1)).toBe("/#acordaos-recentes");
    expect(urlRecentes(2)).toBe("/?pagina=2#acordaos-recentes");
  });
});
