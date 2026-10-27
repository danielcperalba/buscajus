"use client";

export default function Erro({ reset }: { error: Error; reset: () => void }) {
  return (
    <section className="estado estado-erro" role="alert">
      <h1>Algo deu errado</h1>
      <p>Não foi possível mostrar esta página agora.</p>
      <button type="button" onClick={() => reset()}>
        Tentar de novo
      </button>
    </section>
  );
}
