import Link from "next/link";

import type { Filtros as OpcoesFiltros } from "@/api/cliente";
import { CampoRelator } from "@/componentes/CampoRelator";
import { type EstadoBusca, filtrosAtivos, urlBusca } from "@/lib/busca";

type Props = { opcoes?: OpcoesFiltros; estado: EstadoBusca };

type Opcao = { valor: string; rotulo: string; total: number };

function Selecao(props: { nome: string; rotulo: string; opcoes: Opcao[]; valor?: string }) {
  const { nome, rotulo, opcoes, valor } = props;
  return (
    <div className="campo">
      <label htmlFor={`filtro-${nome}`}>{rotulo}</label>
      <select id={`filtro-${nome}`} name={nome} defaultValue={valor ?? ""}>
        <option value="">Todos</option>
        {opcoes.map((opcao) => (
          <option key={opcao.valor} value={opcao.valor}>
            {opcao.rotulo} ({opcao.total})
          </option>
        ))}
        {/* Valor da URL que não está entre as opções (ex.: cache desatualizado). */}
        {valor && !opcoes.some((o) => o.valor === valor) ? (
          <option value={valor}>{valor}</option>
        ) : null}
      </select>
    </div>
  );
}

/**
 * Filtros da busca (F5-06), dentro do mesmo formulário GET: valem na URL e na consulta.
 * Recolhíveis; abertos quando algum está ativo.
 */
export function Filtros({ opcoes, estado }: Props) {
  const ativos = filtrosAtivos(estado);
  const limpar = urlBusca({ q: estado.q, pagina: 1 });
  return (
    <details className="filtros" open={ativos.length > 0}>
      <summary>
        Filtros{ativos.length > 0 ? ` (${ativos.length} ativo${ativos.length > 1 ? "s" : ""})` : ""}
      </summary>
      <div className="filtros-campos">
        <Selecao
          nome="tribunal"
          rotulo="Tribunal"
          opcoes={opcoes?.tribunais ?? []}
          valor={estado.tribunal}
        />
        <Selecao
          nome="orgao"
          rotulo="Órgão julgador"
          opcoes={opcoes?.orgaos ?? []}
          valor={estado.orgao}
        />
        <Selecao
          nome="classe"
          rotulo="Classe"
          opcoes={opcoes?.classes ?? []}
          valor={estado.classe}
        />
        <CampoRelator valor={estado.relator} />
        <div className="campo">
          <label htmlFor="filtro-data_inicio">Julgado a partir de</label>
          <input
            id="filtro-data_inicio"
            name="data_inicio"
            type="date"
            defaultValue={estado.data_inicio}
          />
        </div>
        <div className="campo">
          <label htmlFor="filtro-data_fim">Julgado até</label>
          <input id="filtro-data_fim" name="data_fim" type="date" defaultValue={estado.data_fim} />
        </div>
      </div>
      <div className="filtros-acoes">
        <button type="submit">Aplicar filtros</button>
        {ativos.length > 0 ? <Link href={limpar}>Limpar filtros</Link> : null}
      </div>
      {opcoes === undefined ? (
        <p className="aviso">As opções de filtro não puderam ser carregadas agora.</p>
      ) : null}
    </details>
  );
}
