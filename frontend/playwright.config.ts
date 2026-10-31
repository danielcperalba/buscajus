// Testes E2E do frontend contra a API em modo mock (F6-09).
//
// Sobe a API do backend com dados sintéticos fixos (BUSCAJUS_API__MOCK=true, porta 8100) e o
// Next.js já construído (pnpm build) na porta 3100. Rodar: pnpm e2e.
import { defineConfig, devices } from "@playwright/test";

const API = "http://127.0.0.1:8100";
const SITE = "http://127.0.0.1:3100";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: { baseURL: SITE, trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command:
        "uv run --directory ../backend uvicorn buscajus.api.app:criar_app --factory --port 8100",
      // O mock não usa o banco (a /saude responde 503 sem ele): espera-se pelos filtros.
      url: `${API}/api/v1/filtros`,
      env: { BUSCAJUS_API__MOCK: "true", BUSCAJUS_API__CONSULTAS_POR_MINUTO: "10000" },
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: "pnpm start",
      url: SITE,
      env: { API_URL: API, PORT: "3100", CONTATO_EMAIL: "contato@exemplo.invalid" },
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
});
