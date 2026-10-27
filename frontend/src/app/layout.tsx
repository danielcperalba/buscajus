import type { Metadata } from "next";
import Link from "next/link";

import "./globals.css";

export const metadata: Metadata = {
  title: { default: "BuscaJus", template: "%s | BuscaJus" },
  description:
    "Busca de jurisprudência por contexto, com número do processo e citação, a partir de fontes oficiais.",
};

const NAVEGACAO = [
  { href: "/busca", rotulo: "Busca" },
  { href: "/sobre", rotulo: "Sobre" },
];
const RODAPE = [
  { href: "/sobre", rotulo: "Sobre e fontes" },
  { href: "/privacidade", rotulo: "Privacidade" },
  { href: "/remocao", rotulo: "Solicitar remoção" },
];

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="pt-BR">
      <body>
        <a className="pular-para-conteudo" href="#conteudo">
          Pular para o conteúdo
        </a>
        <header className="cabecalho">
          <div className="largura">
            <Link href="/" className="marca">
              BuscaJus
            </Link>
            <nav aria-label="Principal">
              <ul>
                {NAVEGACAO.map((item) => (
                  <li key={item.href}>
                    <Link href={item.href}>{item.rotulo}</Link>
                  </li>
                ))}
              </ul>
            </nav>
          </div>
        </header>
        <main id="conteudo" className="largura conteudo">
          {children}
        </main>
        <footer className="rodape">
          <div className="largura">
            <p>
              Reprodução de textos de fontes oficiais (DJEN/CNJ e TJDFT). Confira sempre o documento
              original.
            </p>
            <nav aria-label="Institucional">
              <ul>
                {RODAPE.map((item) => (
                  <li key={item.href}>
                    <Link href={item.href}>{item.rotulo}</Link>
                  </li>
                ))}
              </ul>
            </nav>
          </div>
        </footer>
      </body>
    </html>
  );
}
