// Estrutura do texto de ementas e dispositivos para exibição (F5-15): abertura (a classificação
// em caixa alta, "DIREITO CIVIL. APELAÇÃO CÍVEL. …"), tópicos em romanos ("I. CASO EM EXAME"),
// itens numerados ("1. Apelação…") e rótulos do modelo do CNJ ("Tese de julgamento:").
// Só muda a apresentação: o texto exibido é o mesmo da fonte, sem cortes.

export type Bloco =
  | { tipo: "topico"; marcador: string; texto: string }
  | { tipo: "item"; marcador: string; texto: string }
  | { tipo: "rotulo"; rotulo: string; texto: string }
  | { tipo: "paragrafo"; texto: string };

export type TextoEstruturado = { abertura: string | null; blocos: Bloco[] };

const MAIUSCULA = "A-ZÀ-ÖØ-Þ";
const ROMANO = "(?:IX|IV|V?I{1,3}|V|X)";
const ROTULOS =
  "Tese de julgamento|Teses de julgamento|Dispositivos? relevantes? citados?|" +
  "Legisla[çc][ãa]o relevante citada|Jurisprud[êe]ncia relevante citada|" +
  "Resumo em linguagem (?:acess[íi]vel|simples)";
// Títulos fixos do modelo do CNJ, que também aparecem em caixa baixa ("I. Caso em exame").
const TITULOS_CNJ =
  "Caso em exame|Quest(?:ão|ões) em discuss(?:ão|ões)|Raz(?:ões|ão) de decidir|" +
  "Dispositivo(?: e teses?)?";
const TITULOS_CNJ_TODOS = `${TITULOS_CNJ}|${TITULOS_CNJ.toLocaleUpperCase("pt-BR")}`;
const TITULO_CNJ_NO_INICIO = new RegExp(`^(${TITULOS_CNJ})(?=[\\s:.;,\\d]|$)[\\s:.]*`, "i");
// Romano com ponto ou travessão ("I. ", "I – "), seguido de título em caixa alta ou do modelo.
const TOPICO = `${ROMANO}\\s*(?:\\.|[-–—])\\s*(?=[${MAIUSCULA}]{2,}|${TITULOS_CNJ})`;
const ITEM = `\\d{1,2}\\.\\s+(?=["“${MAIUSCULA}])`;
// Item colado ao ponto anterior ("fato.4. As"): exige palavra iniciada por maiúscula seguida de
// minúscula, para não confundir com valores ("10.50").
const ITEM_COLADO = `\\d{1,2}\\.\\s+[${MAIUSCULA}][a-zà-ÿ]`;

// Um marcador só vale no começo do texto ou de uma linha, depois de fim de frase (". ", ": ",
// "; ", aspas) ou depois de um título em caixa alta ("EXAME 1. Apelação"). No DJEN o texto vem
// muitas vezes colado: tópico ou item logo depois do ponto ("DESPROVIDO.I. CASO", "fato.4. As",
// ".Tese de julgamento:") e item grudado no título ("Caso em exame1. Recurso"). Tópico romano
// exige título em caixa alta ou do modelo logo depois; item numerado exige maiúscula ou aspas.
// Assim, "inciso I. Recurso", "Lei 8.078" e iniciais de nomes ("J. V. S.") não viram tópico.
const MARCADOR = new RegExp(
  `(^|\\n|[.;:!?)"”]\\s+|["“]|[${MAIUSCULA}]{2,}\\s+|(?:${TITULOS_CNJ_TODOS})\\s*` +
    `|[.;:_)"”](?=${TOPICO}|${ITEM_COLADO}|(?:${ROTULOS})\\s*:))` +
    `(${TOPICO}|${ITEM}|(?:${ROTULOS})\\s*:\\s*)`,
  "g",
);

type Marca = { inicio: number; fim: number; marcador: string };

function marcas(texto: string): Marca[] {
  const encontradas: Marca[] = [];
  for (const m of texto.matchAll(MARCADOR)) {
    const inicio = (m.index ?? 0) + (m[1]?.length ?? 0);
    encontradas.push({ inicio, fim: inicio + m[2].length, marcador: m[2].trim() });
  }
  return encontradas;
}

/**
 * Título do tópico: um título do modelo do CNJ (em qualquer caixa) ou as palavras em caixa alta
 * do começo; o resto vira parágrafo.
 */
function separarTitulo(texto: string): [string, string] {
  const modelo = TITULO_CNJ_NO_INICIO.exec(texto.trim());
  if (modelo) return [modelo[1], texto.trim().slice(modelo[0].length).trim()];
  const palavras = texto.split(/\s+/).filter(Boolean);
  let fim = 0;
  while (
    fim < palavras.length &&
    palavras[fim] === palavras[fim].toLocaleUpperCase("pt-BR") &&
    new RegExp(`[${MAIUSCULA}]`).test(palavras[fim])
  ) {
    fim++;
  }
  const titulo = palavras
    .slice(0, fim)
    .join(" ")
    .replace(/[:.]+$/, "");
  return [titulo, palavras.slice(fim).join(" ")];
}

function paragrafos(texto: string): Bloco[] {
  return texto
    .split(/\n+/)
    .map((linha) => linha.trim())
    .filter(Boolean)
    .map((linha) => ({ tipo: "paragrafo", texto: linha }));
}

/**
 * Divide o texto em abertura e blocos. Sem nenhum marcador reconhecido, não há abertura: o
 * texto inteiro vira parágrafos (quebras de linha da fonte).
 */
export function estruturarTexto(texto: string): TextoEstruturado {
  const normalizado = texto.replace(/\r\n?/g, "\n").trim();
  const lista = marcas(normalizado);
  if (lista.length === 0) return { abertura: null, blocos: paragrafos(normalizado) };

  const abertura = normalizado.slice(0, lista[0].inicio).trim() || null;
  const blocos: Bloco[] = [];
  lista.forEach((marca, i) => {
    const conteudo = normalizado.slice(marca.fim, lista[i + 1]?.inicio ?? normalizado.length);
    const [primeiro = "", ...resto] = conteudo.split(/\n+/);
    const extras = paragrafos(resto.join("\n"));
    if (marca.marcador.endsWith(":")) {
      blocos.push({
        tipo: "rotulo",
        rotulo: marca.marcador.slice(0, -1).trim(),
        texto: primeiro.trim(),
      });
    } else if (/^\d/.test(marca.marcador) && !TITULO_CNJ_NO_INICIO.test(primeiro.trim())) {
      blocos.push({ tipo: "item", marcador: marca.marcador, texto: primeiro.trim() });
    } else {
      // Romano, ou número seguido de título do modelo ("1. CASO EM EXAME").
      const [titulo, corpo] = separarTitulo(primeiro);
      blocos.push({ tipo: "topico", marcador: marca.marcador, texto: titulo });
      if (corpo) blocos.push({ tipo: "paragrafo", texto: corpo });
    }
    blocos.push(...extras);
  });
  return { abertura, blocos };
}
