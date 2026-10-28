import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { DetalheAcordao } from "@/api/cliente";
import Inicio from "@/app/page";
import Privacidade from "@/app/privacidade/page";
import Sobre from "@/app/sobre/page";
import { CartaoResultado } from "@/componentes/CartaoResultado";
import { AcordaoIndisponivel, Detalhe } from "@/componentes/Detalhe";
import { EstadoErro, EstadoVazio } from "@/componentes/Estados";
import { Filtros } from "@/componentes/Filtros";
import { FormRemocao } from "@/componentes/FormRemocao";
import { lerEstado } from "@/lib/busca";
import { type EstadoPedido, validarPedido } from "@/lib/remocao";
import { violacoesGraves } from "@/testes/axe";
import { RESULTADO_DJEN, RESULTADO_TJDFT } from "@/testes/dados";

// Componente assíncrono de servidor (lê a API): fora do escopo do jsdom; o E2E cobre.
vi.mock("@/componentes/Cobertura", () => ({ Cobertura: () => <p>cobertura</p> }));

vi.mock("next/form", () => ({
  default: (props: React.FormHTMLAttributes<HTMLFormElement>) => <form {...props} />,
}));

const DETALHE: DetalheAcordao = {
  ...RESULTADO_TJDFT,
  relator_designado: "Beltrana de Tal",
  ementa: "DIREITO CIVIL. INVENTÁRIO.\nI. CASO EM EXAME\n1. Partilha da herança.",
  decisao: "CONHECIDO. DESPROVIDO. UNÂNIME.",
  possui_inteiro_teor: true,
};

describe("Detalhe (F5-08)", () => {
  it("mostra ementa, dispositivo, citação, links e o pedido de remoção", () => {
    render(<Detalhe acordao={DETALHE} />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(DETALHE.numero_processo);
    const ementa = screen.getByRole("region", { name: "Ementa" });
    expect(ementa).toHaveTextContent("I. CASO EM EXAME");
    expect(screen.getByRole("region", { name: "Dispositivo" })).toHaveTextContent("UNÂNIME");
    expect(screen.getByRole("region", { name: "Citação" })).toHaveTextContent(DETALHE.citacao);
    expect(screen.getByRole("button", { name: "Copiar citação" })).toBeInTheDocument();
    expect(screen.getByText("Relator para o acórdão").nextElementSibling).toHaveTextContent(
      "Beltrana de Tal",
    );
    expect(screen.getByRole("link", { name: /Ver na fonte oficial/ })).toHaveAttribute(
      "href",
      DETALHE.link_oficial,
    );
    expect(screen.getByRole("link", { name: "Outros acórdãos deste processo" })).toHaveAttribute(
      "href",
      `/processo/${encodeURIComponent(DETALHE.numero_processo)}`,
    );
    expect(screen.getByRole("link", { name: "Solicitar remoção" })).toHaveAttribute(
      "href",
      "/remocao?referencia=%2Facordao%2F2",
    );
    expect(screen.getByText(DETALHE.aviso)).toBeInTheDocument();
  });

  it("sem dispositivo (DJEN), a seção não aparece", () => {
    render(<Detalhe acordao={{ ...DETALHE, ...RESULTADO_DJEN, decisao: null }} />);
    expect(screen.queryByRole("region", { name: "Dispositivo" })).toBeNull();
    expect(screen.getByRole("link", { name: /sistema do tribunal/ })).toBeInTheDocument();
  });

  it("cancelado e removido (410)", () => {
    const { rerender } = render(
      <AcordaoIndisponivel
        indisponivel={{ erro: "cancelado", mensagem: "Cancelada.", link_oficial: "https://x" }}
      />,
    );
    expect(screen.getByRole("heading")).toHaveTextContent("Publicação cancelada");
    expect(screen.getByRole("link", { name: /Consultar a fonte oficial/ })).toBeInTheDocument();
    rerender(
      <AcordaoIndisponivel
        indisponivel={{ erro: "removido", mensagem: "Removido.", link_oficial: null }}
      />,
    );
    expect(screen.getByRole("heading")).toHaveTextContent("Acórdão removido");
    expect(screen.queryByRole("link", { name: /fonte oficial/ })).toBeNull();
  });
});

describe("Remoção (F5-11)", () => {
  it("valida como a API", () => {
    expect(validarPedido({ referencia: "123", motivo: "curto", email: "x" })).toEqual({
      referencia: expect.any(String),
      motivo: expect.any(String),
      email: expect.any(String),
    });
    expect(
      validarPedido({
        referencia: "0001234-56.2099.8.07.9999",
        motivo: "Meu nome aparece no texto.",
        email: "pessoa@exemplo.invalid",
      }),
    ).toEqual({});
  });

  it("mostra os erros ligados aos campos e, enviado, o protocolo", async () => {
    const respostas: EstadoPedido[] = [
      {
        situacao: "invalido",
        valores: { referencia: "x", motivo: "", email: "" },
        erros: { referencia: "Informe o número do processo ou o link do resultado." },
      },
      { situacao: "enviado", protocolo: 42 },
    ];
    const acao = vi.fn(async () => respostas.shift() as EstadoPedido);
    const usuario = userEvent.setup();
    render(<FormRemocao acao={acao} referenciaInicial="/acordao/2" />);
    const referencia = screen.getByLabelText("Número do processo ou link do resultado");
    expect(referencia).toHaveValue("/acordao/2");
    await usuario.click(screen.getByRole("button", { name: "Enviar pedido" }));
    expect(await screen.findByText("Corrija os campos indicados.")).toBeInTheDocument();
    const campo = screen.getByLabelText("Número do processo ou link do resultado");
    expect(campo).toHaveAttribute("aria-invalid", "true");
    expect(campo).toHaveAccessibleDescription(/Informe o número do processo/);
    await usuario.click(screen.getByRole("button", { name: "Enviar pedido" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Protocolo nº 42");
    expect(acao).toHaveBeenCalledTimes(2);
  });

  it("falha da API aparece como alerta, mantendo o que foi digitado", async () => {
    const acao = vi.fn(
      async (): Promise<EstadoPedido> => ({
        situacao: "falhou",
        valores: { referencia: "/acordao/2", motivo: "Meu nome aparece.", email: "a@b.c" },
        mensagem: "Muitos pedidos em pouco tempo. Tente de novo mais tarde.",
      }),
    );
    const usuario = userEvent.setup();
    render(<FormRemocao acao={acao} />);
    await usuario.click(screen.getByRole("button", { name: "Enviar pedido" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Muitos pedidos");
    expect(screen.getByLabelText("Motivo")).toHaveValue("Meu nome aparece.");
  });
});

describe("Acessibilidade (F5-12)", () => {
  const casos: [string, () => React.ReactElement][] = [
    ["início", () => <Inicio />],
    ["sobre", () => <Sobre />],
    ["privacidade", () => <Privacidade />],
    ["detalhe", () => <Detalhe acordao={DETALHE} />],
    [
      "indisponível",
      () => (
        <AcordaoIndisponivel
          indisponivel={{ erro: "removido", mensagem: "x", link_oficial: null }}
        />
      ),
    ],
    [
      "resultados",
      () => (
        <ol>
          <li>
            <CartaoResultado resultado={RESULTADO_TJDFT} />
          </li>
          <li>
            <CartaoResultado resultado={RESULTADO_DJEN} />
          </li>
        </ol>
      ),
    ],
    [
      "filtros",
      () => (
        <form>
          <Filtros estado={lerEstado({ q: "x", tribunal: "TJPR" })} />
        </form>
      ),
    ],
    ["vazio", () => <EstadoVazio filtrando />],
    ["erro", () => <EstadoErro falha={{ status: 429, erro: "limite_excedido", mensagem: "x" }} />],
    ["remoção", () => <FormRemocao acao={async () => ({ situacao: "inicial" })} />],
  ];

  it.each(casos)("%s: sem violações graves do axe", async (_nome, montar) => {
    const { container } = render(<main>{montar()}</main>);
    expect(await violacoesGraves(container)).toEqual([]);
  });

  it("páginas têm um h1", () => {
    for (const Pagina of [Inicio, Sobre, Privacidade]) {
      const { container, unmount } = render(<Pagina />);
      expect(within(container).getAllByRole("heading", { level: 1 })).toHaveLength(1);
      unmount();
    }
  });
});
