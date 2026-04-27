import { defineConfig, devices } from "@playwright/test";
import { execSync } from "child_process";
import { existsSync } from "fs";
import { dirname, resolve } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));

// Auto-install browser deps if not present (Linux devcontainer only)
const LIBS_DIR = "/tmp/playwright-libs";
if (process.platform === "linux" && !existsSync(`${LIBS_DIR}/.installed`)) {
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
    baseURL: "http://localhost:3010",
    headless: true,
    viewport: { width: 1280, height: 720 },
  },
  projects: [
    {
      name: "chromium",
      use: { browserName: "chromium" },
    },
    // Phase B: mobile viewport coverage. Pixel 5 (Android Chrome) +
    // iPhone 13 (iOS Safari) are the canonical mobile-Chrome / mobile-Safari
    // baselines per BSVibe Shared Library Roadmap §B3.
    {
      name: "pixel-5",
      use: { ...devices["Pixel 5"] },
    },
    // iPhone 13 viewport (390×844). We deliberately use Mobile Chromium
    // here rather than WebKit because Playwright's bundled WebKit
    // currently page-launches with a multi-minute cold start on macOS
    // 26+ (DEPENDENCIES_VALIDATED hangs during context creation),
    // making CI intractable. The viewport, user agent, and isMobile
    // flag still match the iPhone 13 spec — the only difference is the
    // engine that renders it. Real-device testing on Safari is covered
    // by the BSVibe canary skill, not this CI suite.
    {
      name: "iphone-13",
      use: {
        browserName: "chromium",
        ...devices["iPhone 13"],
        defaultBrowserType: "chromium",
      },
    },
  ],
  webServer: {
    command: "npm run dev -- --port 3010",
    port: 3010,
    reuseExistingServer: true,
    timeout: 60_000,
  },
});
