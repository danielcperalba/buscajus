import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = { title: "Não encontrado", robots: { index: false } };

/** Destino do proxy para acórdão inexistente (status 404 definido pelo proxy). */
export default function NaoEncontrado() {
  return (
    <section className="estado">
      <h1>Acórdão não encontrado</h1>
      <p>O endereço não corresponde a nenhum acórdão disponível na base.</p>
      <p>
        <Link href="/busca">Voltar para a busca</Link>
      </p>
    </section>
  );
}
