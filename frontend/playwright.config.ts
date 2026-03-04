import { defineConfig } from "@playwright/test";

const FRONTEND_URL = "http://127.0.0.1:5173";
const BACKEND_URL = "http://127.0.0.1:8000/health";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 180_000,
  expect: {
    timeout: 15_000,
  },
  use: {
    baseURL: FRONTEND_URL,
    headless: true,
    trace: "retain-on-failure",
    video: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: [
    {
      command: "./venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000",
      cwd: "../aletheia-backend",
      url: BACKEND_URL,
      timeout: 180_000,
      reuseExistingServer: true,
    },
    {
      command: "npm run dev -- --host 127.0.0.1 --port 5173",
      cwd: ".",
      url: FRONTEND_URL,
      timeout: 120_000,
      reuseExistingServer: true,
    },
  ],
});
