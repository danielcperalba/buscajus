import { describe, expect, it } from "vitest";

import { ipAcrescentadoPeloProxy } from "./ip";

describe("ipAcrescentadoPeloProxy (segurança)", () => {
  it("repassa só o último item, o do proxy reverso", () => {
    expect(ipAcrescentadoPeloProxy("1.2.3.4, 5.6.7.8, 203.0.113.9")).toBe("203.0.113.9");
    expect(ipAcrescentadoPeloProxy("203.0.113.9")).toBe("203.0.113.9");
    expect(ipAcrescentadoPeloProxy("1.2.3.4,2001:db8::1")).toBe("2001:db8::1");
  });

  it("ausente ou malformado: nada", () => {
    for (const valor of [null, undefined, "", "1.2.3.4,", "lixo", "1.2.3.400", "a, b"]) {
      expect(ipAcrescentadoPeloProxy(valor)).toBeUndefined();
    }
  });
});
