import { describe, expect, it } from "vitest";

import { estruturarTexto } from "./ementa";

// Ementas sintéticas no modelo do CNJ (Recomendação 154/2024); nomes são marcadores.
const MODELO_CNJ =
  "DIREITO CIVIL. APELAÇÃO CÍVEL. INVENTÁRIO. PARTILHA DA HERANÇA. RECURSO DESPROVIDO. " +
  "I. CASO EM EXAME 1. Apelação contra sentença que homologou a partilha. " +
  "II. QUESTÃO EM DISCUSSÃO 2. A questão consiste em saber se o imóvel integra o espólio. " +
  "III. RAZÕES DE DECIDIR 3. O imóvel foi adquirido antes do casamento, nos termos do art. 1.661 do CC. " +
  "4. Precedentes do inciso I. Não há reparo. " +
  "IV. DISPOSITIVO E TESE 5. Recurso desprovido. " +
  "Tese de julgamento: “1. O bem adquirido antes do casamento não se comunica.” " +
  "Dispositivos relevantes citados: CC, art. 1.661. " +
  "Jurisprudência relevante citada: STJ, REsp 9.999/XX.";

describe("estruturarTexto (F5-15)", () => {
  it("separa abertura, tópicos romanos, itens numerados e rótulos", () => {
    const { abertura, blocos } = estruturarTexto(MODELO_CNJ);
    expect(abertura).toBe(
      "DIREITO CIVIL. APELAÇÃO CÍVEL. INVENTÁRIO. PARTILHA DA HERANÇA. RECURSO DESPROVIDO.",
    );
    expect(
      blocos.map((b) =>
        b.tipo === "rotulo" ? `${b.rotulo}:` : b.tipo === "paragrafo" ? "¶" : b.marcador,
      ),
    ).toEqual([
      "I.",
      "1.",
      "II.",
      "2.",
      "III.",
      "3.",
      "4.",
      "IV.",
      "5.",
      "Tese de julgamento:",
      "1.",
      "Dispositivos relevantes citados:",
      "Jurisprudência relevante citada:",
    ]);
    expect(blocos[0]).toEqual({ tipo: "topico", marcador: "I.", texto: "CASO EM EXAME" });
    expect(blocos[5]).toEqual({
      tipo: "item",
      marcador: "3.",
      texto: "O imóvel foi adquirido antes do casamento, nos termos do art. 1.661 do CC.",
    });
  });

  it("não perde nem acrescenta texto", () => {
    const { abertura, blocos } = estruturarTexto(MODELO_CNJ);
    const remontado = [
      abertura,
      ...blocos.map((b) =>
        b.tipo === "rotulo"
          ? `${b.rotulo}: ${b.texto}`
          : b.tipo === "paragrafo"
            ? b.texto
            : `${b.marcador} ${b.texto}`,
      ),
    ].join(" ");
    const sem = (t: string) => t.replace(/\s+/g, "");
    expect(sem(remontado)).toBe(sem(MODELO_CNJ));
  });

  it("ignora números de lei, incisos e iniciais de nomes", () => {
    const texto =
      "Recurso de F. J. S. contra a Lei 8.078/90, art. 6. o pedido segue o inciso I. Recurso " +
      "conhecido. Valor de R$ 1.000,00.";
    expect(estruturarTexto(texto)).toEqual({
      abertura: null,
      blocos: [{ tipo: "paragrafo", texto }],
    });
  });

  it("modelo antigo, sem tópicos romanos: itens numerados depois da abertura", () => {
    const { abertura, blocos } = estruturarTexto(
      "APELAÇÃO CÍVEL. CONSUMIDOR. 1. A negativação foi indevida. 2. Dano moral configurado. " +
        "3. Recurso conhecido e desprovido.",
    );
    expect(abertura).toBe("APELAÇÃO CÍVEL. CONSUMIDOR.");
    expect(blocos.map((b) => b.tipo)).toEqual(["item", "item", "item"]);
  });

  it("tópico seguido de texto sem item numerado: o corpo vira parágrafo", () => {
    const { blocos } = estruturarTexto("PENAL. I. CASO EM EXAME Trata-se de apelação.");
    expect(blocos).toEqual([
      { tipo: "topico", marcador: "I.", texto: "CASO EM EXAME" },
      { tipo: "paragrafo", texto: "Trata-se de apelação." },
    ]);
  });

  it("variações reais do modelo: colado ao ponto, caixa baixa, travessão e título numerado", () => {
    const titulos = (texto: string) =>
      estruturarTexto(texto)
        .blocos.filter((b) => b.tipo === "topico")
        .map((b) => (b.tipo === "topico" ? `${b.marcador} ${b.texto}` : ""));
    expect(titulos("CIVIL. DESPROVIDO.I. CASO EM EXAME 1. Apelação.")).toEqual([
      "I. CASO EM EXAME",
    ]);
    expect(
      titulos("CIVIL. I. Caso em exame 1. Apelação. II. Questão em discussão: 2. Saber se cabe."),
    ).toEqual(["I. Caso em exame", "II. Questão em discussão"]);
    expect(titulos("CIVIL. I – CASO EM EXAME 1. Apelação.")).toEqual(["I – CASO EM EXAME"]);
    expect(titulos("CIVIL. 1. CASO EM EXAME: Apelação. 2. RAZÕES DE DECIDIR Mantida.")).toEqual([
      "1. CASO EM EXAME",
      "2. RAZÕES DE DECIDIR",
    ]);
  });

  it("texto colado do DJEN: item grudado no título e marcadores logo depois do ponto", () => {
    const { abertura, blocos } = estruturarTexto(
      "Ementa: Direito civil. Recurso desprovido. I. Caso em exame1. Apelação contra sentença." +
        "II. Questão em discussão2. Saber se cabe a partilha.3. Outra questão." +
        "Tese de julgamento: O bem não se comunica._____Resumo em linguagem acessível: Explicação.",
    );
    expect(abertura).toBe("Ementa: Direito civil. Recurso desprovido.");
    expect(
      blocos.map((b) =>
        b.tipo === "rotulo"
          ? `${b.rotulo}:`
          : b.tipo === "paragrafo"
            ? "¶"
            : `${b.marcador} ${b.texto}`,
      ),
    ).toEqual([
      "I. Caso em exame",
      "1. Apelação contra sentença.",
      "II. Questão em discussão",
      "2. Saber se cabe a partilha.",
      "3. Outra questão.",
      "Tese de julgamento:",
      "Resumo em linguagem acessível:",
    ]);
  });

  it("valores e decimais colados ao ponto não viram item", () => {
    const texto = "Condenação. Valor de R$ 10.50.000,00 mantido.10.50 por cento.";
    expect(estruturarTexto(texto).abertura).toBeNull();
  });

  it("respeita quebras de linha da fonte", () => {
    const { abertura, blocos } = estruturarTexto(
      "Primeira linha.\nSegunda linha.\r\n\r\nTerceira.",
    );
    expect(abertura).toBeNull();
    expect(blocos.map((b) => (b.tipo === "paragrafo" ? b.texto : ""))).toEqual([
      "Primeira linha.",
      "Segunda linha.",
      "Terceira.",
    ]);
  });
});
