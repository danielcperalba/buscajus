// Resultados sintéticos para os testes (nomes genéricos, processos do ano 2099).
import type { ResultadoBusca } from "@/api/cliente";

export const RESULTADO_TJDFT: ResultadoBusca = {
  id: 2,
  fonte: "tjdft",
  tribunal: "TJDFT",
  numero_processo: "0001234-56.2099.8.07.9999",
  orgao_julgador: "3ª Turma Cível",
  classe: { codigo: 198, nome: "Apelação Cível" },
  relator: "Beltrano de Tal",
  relator_designado: null,
  turma_recursal: false,
  data_julgamento: "2026-10-08",
  data_publicacao: "2026-10-21",
  data_disponibilizacao: null,
  link_oficial: "https://jurisdf.tjdft.jus.br/acordaos/00000000-2099-4000-8000-000000000002",
  link_tribunal: null,
  citacao:
    "TJDFT, 3ª Turma Cível, Apelação Cível nº 0001234-56.2099.8.07.9999, Rel. Beltrano de Tal, " +
    "j. 08/10/2026, publ. PJe 21/10/2026.",
  aviso: "Texto reproduzido da fonte oficial. Consulte o documento original.",
  trecho: "DIREITO CIVIL. INVENTÁRIO. PARTILHA DA <mark>HERANÇA</mark> &amp; outros.",
};

export const RESULTADO_DJEN: ResultadoBusca = {
  ...RESULTADO_TJDFT,
  id: 1,
  fonte: "djen",
  tribunal: "TJPR",
  numero_processo: "0011412-15.2099.8.16.9999",
  orgao_julgador: "3ª Turma Recursal dos Juizados Especiais",
  classe: { codigo: 460, nome: "Recurso Inominado Cível" },
  relator: "Fulano de Tal",
  data_publicacao: null,
  data_disponibilizacao: "2026-10-14",
  link_oficial: "https://comunicaapi.pje.jus.br/api/v1/comunicacao/exemplo/certidao",
  link_tribunal: "https://projudi.exemplo.invalid/documento",
  citacao: "TJPR, ..., DJEN de 14/10/2026.",
};
