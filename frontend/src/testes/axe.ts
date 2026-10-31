// Checagem automatizada de acessibilidade (F5-12) com o axe-core.
import axe from "axe-core";

/**
 * Violações graves (``serious`` ou ``critical``) no elemento. O contraste de cores não é
 * medido aqui: o jsdom não calcula estilos; os tokens de cor do globals.css foram escolhidos
 * com contraste AA.
 */
export async function violacoesGraves(elemento: Element): Promise<string[]> {
  const resultado = await axe.run(elemento, {
    rules: { "color-contrast": { enabled: false }, region: { enabled: false } },
  });
  return resultado.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => `${v.id}: ${v.help} (${v.nodes.length})`);
}
