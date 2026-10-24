import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "BuscaJus",
  description:
    "Busca de jurisprudência por contexto, com número do processo e citação, a partir de fontes oficiais.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="pt-BR">
      <body>{children}</body>
    </html>
  );
}
