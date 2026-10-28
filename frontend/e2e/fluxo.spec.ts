// F6-09: fluxo principal contra a API mock (dados sintéticos fixos de buscajus.api.mock).
import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test("buscar → copiar citação → abrir detalhe → link oficial", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.goto("/");
  await page
    .getByLabel("Descreva a situação ou informe o número do processo")
    .fill("disputa por herança familiar");
  await page.getByRole("button", { name: "Buscar" }).click();

  await expect(page).toHaveURL(/\/busca\?q=disputa\+por\+heran%C3%A7a\+familiar/);
  const cartao = page.getByRole("article").first();
  await expect(cartao).toContainText("TJDFT");
  await expect(cartao.locator("mark").first()).toHaveText("HERANÇA");

  await cartao.getByRole("button", { name: "Copiar citação" }).click();
  await expect(cartao.getByRole("status")).toHaveText("Citação copiada.");
  const copiada = await page.evaluate(() => navigator.clipboard.readText());
  expect(copiada).toMatch(
    /^TJDFT, 3ª Turma Cível, Apelação Cível nº .*, publ\. PJe 21\/10\/2026\.$/,
  );

  await cartao.getByRole("heading", { level: 2 }).getByRole("link").click();
  await expect(page).toHaveURL(/\/acordao\/2$/);
  await expect(page.getByRole("heading", { level: 1 })).toContainText("2099.8.07.9999");
  await expect(page.getByRole("region", { name: "Ementa" })).toContainText("PARTILHA DA HERANÇA");
  await expect(page.getByRole("link", { name: /Ver na fonte oficial/ })).toHaveAttribute(
    "href",
    /^https:\/\/jurisdf\.tjdft\.jus\.br\/acordaos\//,
  );
});

test("filtros e paginação ficam na URL", async ({ page }) => {
  await page.goto("/busca?q=a");
  await page.getByText("Filtros", { exact: true }).click();
  await page.getByLabel("Tribunal").selectOption("TJPR");
  await page.getByRole("button", { name: "Aplicar filtros" }).click();
  await expect(page).toHaveURL(/tribunal=TJPR/);
  const cartoes = page.getByRole("article");
  await expect(cartoes).toHaveCount(1);
  await expect(cartoes.first()).toContainText("TJPR");
  await expect(page.getByLabel("Tribunal")).toHaveValue("TJPR");
});

test("busca por número de processo", async ({ page }) => {
  await page.goto("/busca?q=0005678");
  // Só o sequencial é ambíguo: vira busca textual sem resultado.
  await expect(page.getByRole("heading", { name: "Nenhum acórdão encontrado" })).toBeVisible();
  await page.goto("/busca?q=processo+0005678-35.2099.8.07.9999");
  await expect(page.getByRole("status").first()).toContainText(
    "do processo 0005678-35.2099.8.07.9999",
  );
});

test("status HTTP real do detalhe: 200, 410 e 404", async ({ request }) => {
  expect((await request.get("/acordao/2")).status()).toBe(200);
  const removido = await request.get("/acordao/4");
  expect(removido.status()).toBe(410);
  expect(await removido.text()).toContain("Acórdão removido");
  expect((await request.get("/acordao/5")).status()).toBe(410);
  const inexistente = await request.get("/acordao/99");
  expect(inexistente.status()).toBe(404);
  expect(await inexistente.text()).toContain("Acórdão não encontrado");
  expect((await request.get("/acordao/abc")).status()).toBe(404);
});

test("pedido de remoção a partir do detalhe", async ({ page }) => {
  await page.goto("/acordao/2");
  await page.getByRole("main").getByRole("link", { name: "Solicitar remoção" }).click();
  await expect(page.getByLabel("Número do processo ou link do resultado")).toHaveValue(
    "/acordao/2",
  );
  await expect(page.getByText("contato@exemplo.invalid")).toBeVisible();
  await page.getByLabel("Motivo").fill("Meu nome aparece no texto da ementa.");
  await page.getByLabel("E-mail para a resposta").fill("pessoa@exemplo.invalid");
  await page.getByRole("button", { name: "Enviar pedido" }).click();
  await expect(page.getByRole("status")).toContainText("Protocolo nº");
});

for (const caminho of [
  "/",
  "/busca?q=heran%C3%A7a",
  "/acordao/3",
  "/remocao",
  "/sobre",
  "/privacidade",
]) {
  test(`acessibilidade (axe, com contraste) em ${caminho}`, async ({ page }) => {
    await page.goto(caminho);
    await page.waitForLoadState("networkidle");
    const resultado = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
    const graves = resultado.violations.filter(
      (v) => v.impact === "serious" || v.impact === "critical",
    );
    expect(graves.map((v) => `${v.id}: ${v.nodes.length}`)).toEqual([]);
  });
}

test("/sobre mostra a cobertura lida da API (F7-04)", async ({ page }) => {
  await page.goto("/sobre");
  const tabela = page.getByRole("table", { name: "Acórdãos disponíveis por tribunal e fonte" });
  await expect(tabela.getByRole("row", { name: /TJDFT/ })).toContainText("Jurisprudência do TJDFT");
  await expect(tabela.getByRole("row", { name: /TJPR/ })).toContainText("06/10/2026 a 06/10/2026");
});
