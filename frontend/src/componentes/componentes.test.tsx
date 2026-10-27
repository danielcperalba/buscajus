import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CampoRelator } from "@/componentes/CampoRelator";
import { CartaoResultado } from "@/componentes/CartaoResultado";
import { CopiarCitacao } from "@/componentes/CopiarCitacao";
import { AvisoLimite, Carregando, EstadoErro, EstadoVazio } from "@/componentes/Estados";
import { Filtros } from "@/componentes/Filtros";
import { Paginacao } from "@/componentes/Paginacao";
import { lerEstado } from "@/lib/busca";
import { RESULTADO_DJEN, RESULTADO_TJDFT } from "@/testes/dados";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

/** Valor do metadado com o rótulo dado (pares dt/dd do cartão). */
function metadado(cartao: HTMLElement, rotulo: string): string | null | undefined {
  const termo = within(cartao).queryByText(rotulo, { selector: "dt" });
  return termo?.nextElementSibling?.textContent;
}

describe("CartaoResultado (F5-04)", () => {
  it("mostra número, metadados, trecho destacado, links e aviso", () => {
    render(<CartaoResultado resultado={RESULTADO_TJDFT} />);
    const cartao = screen.getByRole("article");
    const titulo = within(cartao).getByRole("heading", { level: 2 });
    expect(titulo).toHaveTextContent("0001234-56.2099.8.07.9999");
    expect(within(titulo).getByRole("link")).toHaveAttribute("href", "/acordao/2");
    expect(metadado(cartao, "Tribunal")).toBe("TJDFT");
    expect(metadado(cartao, "Órgão julgador")).toBe("3ª Turma Cível");
    expect(metadado(cartao, "Classe")).toBe("Apelação Cível");
    expect(metadado(cartao, "Relator")).toBe("Beltrano de Tal");
    expect(metadado(cartao, "Julgado em")).toBe("08/10/2026");
    expect(metadado(cartao, "Publicado em")).toBe("21/10/2026");
    expect(metadado(cartao, "Disponibilizado no DJEN em")).toBeUndefined();
    const marca = cartao.querySelector("mark");
    expect(marca?.textContent).toBe("HERANÇA");
    expect(cartao).toHaveTextContent("PARTILHA DA HERANÇA & outros.");
    const oficial = within(cartao).getByRole("link", { name: /Ver na fonte oficial/ });
    expect(oficial).toHaveAttribute("href", RESULTADO_TJDFT.link_oficial);
    expect(oficial).toHaveAttribute("target", "_blank");
    expect(oficial).toHaveAttribute("rel", "noopener noreferrer");
    expect(within(cartao).queryByRole("link", { name: /sistema do tribunal/ })).toBeNull();
    expect(cartao).toHaveTextContent("Texto reproduzido da fonte oficial");
  });

  it("DJEN: disponibilização e link para o sistema do tribunal", () => {
    render(<CartaoResultado resultado={RESULTADO_DJEN} />);
    const cartao = screen.getByRole("article");
    expect(metadado(cartao, "Disponibilizado no DJEN em")).toBe("14/10/2026");
    expect(metadado(cartao, "Publicado em")).toBeUndefined();
    expect(within(cartao).getByRole("link", { name: /sistema do tribunal/ })).toHaveAttribute(
      "href",
      RESULTADO_DJEN.link_tribunal,
    );
  });

  it("relator designado aparece como relator para o acórdão", () => {
    render(
      <CartaoResultado resultado={{ ...RESULTADO_TJDFT, relator_designado: "Beltrana de Tal" }} />,
    );
    expect(metadado(screen.getByRole("article"), "Relator")).toBe(
      "Beltrana de Tal (relator para o acórdão)",
    );
  });

  it("nenhum HTML além de <mark> chega ao trecho", () => {
    const perigoso = {
      ...RESULTADO_TJDFT,
      trecho: '<img src=x onerror="alert(1)"> <mark>a</mark>',
    };
    render(<CartaoResultado resultado={perigoso} />);
    const trecho = document.querySelector(".cartao-trecho");
    expect(trecho?.querySelector("img")).toBeNull();
    expect(trecho?.querySelectorAll("mark")).toHaveLength(1);
  });
});

describe("CopiarCitacao (F5-05)", () => {
  it("copia exatamente a citação, com aviso para leitores de tela", async () => {
    const usuario = userEvent.setup();
    const escrever = vi.spyOn(navigator.clipboard, "writeText");
    render(<CopiarCitacao citacao={RESULTADO_TJDFT.citacao} />);
    await usuario.click(screen.getByRole("button", { name: "Copiar citação" }));
    expect(escrever).toHaveBeenCalledWith(RESULTADO_TJDFT.citacao);
    expect(screen.getByRole("status")).toHaveTextContent("Citação copiada.");
    expect(screen.getByRole("button")).toHaveTextContent("Copiada!");
  });

  it("funciona pelo teclado", async () => {
    const usuario = userEvent.setup();
    const escrever = vi.spyOn(navigator.clipboard, "writeText");
    render(<CopiarCitacao citacao="TJDFT, citação." />);
    await usuario.tab();
    expect(screen.getByRole("button")).toHaveFocus();
    await usuario.keyboard("{Enter}");
    expect(escrever).toHaveBeenCalledWith("TJDFT, citação.");
  });

  it("se a cópia falha, mostra o texto para copiar manualmente", async () => {
    const usuario = userEvent.setup();
    vi.spyOn(navigator.clipboard, "writeText").mockRejectedValue(new Error("negado"));
    render(<CopiarCitacao citacao="TJDFT, citação." />);
    await usuario.click(screen.getByRole("button"));
    expect(screen.getByRole("status")).toHaveTextContent("Não foi possível copiar");
    expect(screen.getByText("TJDFT, citação.")).toBeInTheDocument();
  });
});

describe("Paginação e estados (F5-07)", () => {
  it("links preservam a busca e marcam a página atual", () => {
    const estado = lerEstado({ q: "herança", tribunal: "TJDFT", pagina: "2" });
    render(<Paginacao estado={estado} total={45} />);
    const nav = screen.getByRole("navigation", { name: "Páginas de resultados" });
    expect(within(nav).getByRole("link", { name: "Anterior" })).toHaveAttribute(
      "href",
      "/busca?q=heran%C3%A7a&tribunal=TJDFT",
    );
    expect(within(nav).getByRole("link", { name: "Próxima" })).toHaveAttribute(
      "href",
      "/busca?q=heran%C3%A7a&tribunal=TJDFT&pagina=3",
    );
    expect(nav.querySelector('[aria-current="page"]')).toHaveTextContent("2");
    expect(within(nav).getAllByRole("link", { name: /Página\s?\d/ })).toHaveLength(2);
  });

  it("sem paginação para uma página só", () => {
    const { container } = render(<Paginacao estado={lerEstado({ q: "x" })} total={20} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("estado vazio sugere reformular e tirar filtros", () => {
    render(<EstadoVazio filtrando />);
    expect(screen.getByRole("heading", { name: "Nenhum acórdão encontrado" })).toBeInTheDocument();
    expect(screen.getByText(/Tire alguns filtros/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "disputa por herança familiar" })).toHaveAttribute(
      "href",
      "/busca?q=disputa+por+heran%C3%A7a+familiar",
    );
  });

  it("erro de limite de taxa e erro genérico", () => {
    const { rerender } = render(
      <EstadoErro falha={{ status: 429, erro: "limite_excedido", mensagem: "x" }} />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Aguarde um minuto");
    rerender(<EstadoErro falha={{ status: 0, erro: "indisponivel", mensagem: "x" }} />);
    expect(screen.getByRole("alert")).toHaveTextContent("indisponível no momento");
  });

  it("aviso de limite só com 200 resultados", () => {
    const { container, rerender } = render(<AvisoLimite total={199} />);
    expect(container).toBeEmptyDOMElement();
    rerender(<AvisoLimite total={200} />);
    expect(screen.getByText(/200 acórdãos mais relevantes/)).toBeInTheDocument();
  });

  it("carregando é anunciado", () => {
    render(<Carregando />);
    expect(screen.getByRole("status")).toHaveTextContent("Buscando acórdãos");
  });
});

describe("Filtros (F5-06)", () => {
  const opcoes = {
    tribunais: [
      { valor: "TJDFT", rotulo: "TJDFT", total: 4 },
      { valor: "TJPR", rotulo: "TJPR", total: 1 },
    ],
    orgaos: [{ valor: "3ª Turma Cível", rotulo: "3ª Turma Cível", total: 2 }],
    classes: [{ valor: "198", rotulo: "Apelação Cível", total: 2 }],
  };

  it("campos com nome dos parâmetros da URL e valores atuais", () => {
    const estado = lerEstado({
      q: "x",
      tribunal: "TJPR",
      classe: "198",
      data_inicio: "2026-10-01",
    });
    render(<Filtros opcoes={opcoes} estado={estado} />);
    expect(screen.getByLabelText("Tribunal")).toHaveValue("TJPR");
    expect(screen.getByLabelText("Tribunal")).toHaveAttribute("name", "tribunal");
    expect(screen.getByLabelText("Classe")).toHaveValue("198");
    expect(screen.getByLabelText("Órgão julgador")).toHaveValue("");
    expect(screen.getByLabelText("Julgado a partir de")).toHaveValue("2026-10-01");
    expect(screen.getByLabelText("Relator")).toHaveAttribute("name", "relator");
    expect(screen.getByText("Filtros (3 ativos)")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Limpar filtros" })).toHaveAttribute(
      "href",
      "/busca?q=x",
    );
  });

  it("sem opções da API, os campos continuam e há um aviso", () => {
    render(<Filtros estado={lerEstado({ q: "x" })} />);
    expect(screen.getByLabelText("Tribunal")).toBeInTheDocument();
    expect(screen.getByText(/não puderam ser carregadas/)).toBeInTheDocument();
  });
});

describe("CampoRelator (F5-06)", () => {
  it("sugere relatores a partir de duas letras", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const buscar = vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify([{ nome: "Fulano de Tal", chave: "fulano de tal" }])),
      );
    vi.stubGlobal("fetch", buscar);
    const usuario = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<CampoRelator />);
    await usuario.type(screen.getByLabelText("Relator"), "f");
    await act(() => vi.advanceTimersByTimeAsync(300));
    expect(buscar).not.toHaveBeenCalled();
    await usuario.type(screen.getByLabelText("Relator"), "u");
    await act(() => vi.advanceTimersByTimeAsync(300));
    expect(buscar).toHaveBeenCalledWith("/api/relatores?prefixo=fu", expect.anything());
    expect(document.querySelector("datalist option")).toHaveAttribute("value", "Fulano de Tal");
    vi.useRealTimers();
  });
});
