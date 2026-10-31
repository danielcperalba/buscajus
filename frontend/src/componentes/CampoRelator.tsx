"use client";

import { useEffect, useId, useState } from "react";

type Sugestao = { nome: string; chave: string };

const ESPERA_MS = 250;

/**
 * Filtro de relator com sugestões (F5-06). As sugestões vêm de /api/relatores (route handler
 * do próprio site, que consulta a API); o valor enviado é o nome, que a API normaliza.
 */
export function CampoRelator({ valor }: { valor?: string }) {
  const [texto, setTexto] = useState(valor ?? "");
  // A resposta guarda o prefixo a que pertence: sugestões de um prefixo antigo não aparecem.
  const [resposta, setResposta] = useState<{ prefixo: string; itens: Sugestao[] }>({
    prefixo: "",
    itens: [],
  });
  const lista = useId();
  const prefixo = texto.trim();
  const sugestoes = prefixo.length >= 2 && resposta.prefixo === prefixo ? resposta.itens : [];

  useEffect(() => {
    if (prefixo.length < 2) return;
    const controle = new AbortController();
    const espera = setTimeout(async () => {
      try {
        const recebida = await fetch(`/api/relatores?prefixo=${encodeURIComponent(prefixo)}`, {
          signal: controle.signal,
        });
        const itens = recebida.ok ? ((await recebida.json()) as Sugestao[]) : [];
        setResposta({ prefixo, itens });
      } catch {
        // Cancelada ou sem rede: o campo continua aceitando texto livre.
      }
    }, ESPERA_MS);
    return () => {
      clearTimeout(espera);
      controle.abort();
    };
  }, [prefixo]);

  return (
    <div className="campo">
      <label htmlFor="filtro-relator">Relator</label>
      <input
        id="filtro-relator"
        name="relator"
        type="text"
        list={lista}
        value={texto}
        onChange={(evento) => setTexto(evento.target.value)}
        autoComplete="off"
        maxLength={100}
      />
      <datalist id={lista}>
        {sugestoes.map((sugestao) => (
          <option key={sugestao.chave} value={sugestao.nome} />
        ))}
      </datalist>
    </div>
  );
}
