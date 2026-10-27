import type { Metadata } from "next";

export const metadata: Metadata = { title: "Sobre" };

// Conteúdo no F5-10 (bloco P).
export default function Sobre() {
  return (
    <article>
      <h1>Sobre o BuscaJus</h1>
      <p>Página em construção: fontes, cobertura por tribunal e período.</p>
    </article>
  );
}
