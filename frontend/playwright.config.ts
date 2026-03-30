import { defineConfig } from "@playwright/test";
import { execSync } from "child_process";
import { existsSync } from "fs";
import { dirname, resolve } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));

// Auto-install browser deps if not present (no-root environments)
const LIBS_DIR = "/tmp/playwright-libs";
if (!existsSync(`${LIBS_DIR}/.installed`)) {
  const script = resolve(__dirname, "scripts/install-playwright-deps.sh");
  if (existsSync(script)) {
    execSync(`bash ${script}`, { stdio: "inherit" });
  }
}

// Set env vars for browser runtime if local libs exist
if (existsSync(LIBS_DIR)) {
  const libPath = `${LIBS_DIR}/usr/lib/aarch64-linux-gnu:${LIBS_DIR}/lib/aarch64-linux-gnu`;
  process.env.LD_LIBRARY_PATH = process.env.LD_LIBRARY_PATH
    ? `${libPath}:${process.env.LD_LIBRARY_PATH}`
    : libPath;
  if (existsSync(`${LIBS_DIR}/etc/fonts/fonts.conf`)) {
    process.env.FONTCONFIG_FILE = `${LIBS_DIR}/etc/fonts/fonts.conf`;
  }
}

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  retries: 0,
  use: {
    baseURL: "http://localhost:5173",
    headless: true,
    viewport: { width: 1280, height: 720 },
  },
  projects: [
    {
      name: "chromium",
      use: { browserName: "chromium" },
    },
  ],
  webServer: {
    command: "pnpm dev",
    port: 5173,
    reuseExistingServer: true,
    timeout: 15_000,
  },
});
