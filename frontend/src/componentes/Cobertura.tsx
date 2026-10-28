import { obterCobertura } from "@/api/cliente";
import { formatarData } from "@/lib/busca";

/** Cobertura por tribunal e fonte, lida da base (F7-04). */
export async function Cobertura() {
  const resposta = await obterCobertura();
  if (resposta.falha) {
    return <p>A cobertura não pôde ser carregada agora.</p>;
  }
  if (resposta.dados.length === 0) {
    return <p>Ainda não há acórdãos disponíveis na base.</p>;
  }
  return (
    <table className="cobertura">
      <caption className="visualmente-oculto">Acórdãos disponíveis por tribunal e fonte</caption>
      <thead>
        <tr>
          <th scope="col">Tribunal</th>
          <th scope="col">Fonte</th>
          <th scope="col">Acórdãos</th>
          <th scope="col">Período (data de julgamento ou publicação)</th>
        </tr>
      </thead>
      <tbody>
        {resposta.dados.map((linha) => (
          <tr key={`${linha.tribunal}-${linha.fonte}`}>
            <th scope="row">{linha.tribunal}</th>
            <td>
              <a href={linha.fonte_url} target="_blank" rel="noopener noreferrer">
                {linha.fonte_nome}
                <span className="visualmente-oculto"> (abre em nova aba)</span>
              </a>
            </td>
            <td>{linha.acordaos.toLocaleString("pt-BR")}</td>
            <td>
              {formatarData(linha.desde) ?? "—"} a {formatarData(linha.ate) ?? "—"}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
