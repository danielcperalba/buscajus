import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = { title: "Indisponível", robots: { index: false } };

/** Destino do proxy quando a API está fora do ar ou lenta (status 503 definido pelo proxy). */
export default function Indisponivel() {
  return (
    <section className="estado estado-erro" role="alert">
      <h1>Serviço temporariamente indisponível</h1>
      <p>Não foi possível abrir este acórdão agora. Tente de novo em alguns instantes.</p>
      <p>
        <Link href="/">Voltar para a busca</Link>
      </p>
    </section>
  );
}
