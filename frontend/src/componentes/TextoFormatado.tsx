import { type Bloco, estruturarTexto } from "@/lib/ementa";

function BlocoTexto({ bloco }: { bloco: Bloco }) {
  switch (bloco.tipo) {
    case "topico":
      return (
        <h3 className="texto-topico">
          {bloco.marcador} {bloco.texto}
        </h3>
      );
    case "item":
      return (
        <p className="texto-item">
          <strong>{bloco.marcador}</strong> {bloco.texto}
        </p>
      );
    case "rotulo":
      return (
        <p>
          <strong>{bloco.rotulo}:</strong> {bloco.texto}
        </p>
      );
    default:
      return <p>{bloco.texto}</p>;
  }
}

/**
 * Ementa ou dispositivo em parágrafos, respeitando os tópicos da fonte (F5-15). A abertura
 * (classificação em caixa alta) fica num tom mais claro, separada do restante do caso.
 */
export function TextoFormatado({ texto }: { texto: string }) {
  const { abertura, blocos } = estruturarTexto(texto);
  return (
    <div className="texto-formatado">
      {abertura ? <p className="texto-abertura">{abertura}</p> : null}
      {blocos.map((bloco, i) => (
        <BlocoTexto key={i} bloco={bloco} />
      ))}
    </div>
  );
}
