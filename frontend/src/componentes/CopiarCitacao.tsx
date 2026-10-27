"use client";

import { useEffect, useRef, useState } from "react";

type Estado = "pronto" | "copiado" | "falhou";

const MENSAGENS: Record<Estado, string> = {
  pronto: "",
  copiado: "Citação copiada.",
  falhou: "Não foi possível copiar. Selecione o texto da citação e copie manualmente.",
};

async function copiar(texto: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(texto);
    return;
  }
  // Navegadores sem a API de área de transferência (ou fora de HTTPS).
  const area = document.createElement("textarea");
  area.value = texto;
  area.setAttribute("readonly", "");
  area.style.position = "fixed";
  area.style.opacity = "0";
  document.body.append(area);
  area.select();
  const ok = document.execCommand("copy");
  area.remove();
  if (!ok) throw new Error("cópia recusada");
}

/** Copia exatamente o campo ``citacao`` da API (F5-05). */
export function CopiarCitacao({ citacao }: { citacao: string }) {
  const [estado, setEstado] = useState<Estado>("pronto");
  const temporizador = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      if (temporizador.current) clearTimeout(temporizador.current);
    },
    [],
  );

  async function aoClicar() {
    try {
      await copiar(citacao);
      setEstado("copiado");
    } catch {
      setEstado("falhou");
    }
    if (temporizador.current) clearTimeout(temporizador.current);
    temporizador.current = setTimeout(() => setEstado("pronto"), 4000);
  }

  return (
    <span className="copiar-citacao">
      <button type="button" onClick={aoClicar}>
        {estado === "copiado" ? "Copiada!" : "Copiar citação"}
      </button>
      <span className="visualmente-oculto" role="status" aria-live="polite">
        {MENSAGENS[estado]}
      </span>
      {estado === "falhou" ? <span className="citacao-texto">{citacao}</span> : null}
    </span>
  );
}
