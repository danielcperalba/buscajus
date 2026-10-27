import Link from "next/link";

export default function NaoEncontrada() {
  return (
    <section className="estado">
      <h1>Página não encontrada</h1>
      <p>
        <Link href="/">Voltar para a busca</Link>
      </p>
    </section>
  );
}
