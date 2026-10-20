import { defineConfig, devices } from "@playwright/test";

// End-to-end tests run against a running app: the Docker image with SQL Server in CI,
// or `docker compose up` locally. Set E2E_BASE_URL to point elsewhere.
export default defineConfig({
  testDir: "e2e",
  timeout: 30_000,
  retries: process.env.CI ? 1 : 0,
  // One worker: the history test loads data the other projects then read.
  workers: 1,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:8000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "phone", use: { ...devices["Pixel 7"] } },
  ],
});
