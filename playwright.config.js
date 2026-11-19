import { defineConfig, devices } from "@playwright/test";

const PORT = 8099;
export default defineConfig({
  testDir: "tests/e2e",
  timeout: 60_000,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    ...devices["Pixel 7"],
    permissions: ["camera", "geolocation", "microphone"],
    geolocation: { latitude: 9.0314, longitude: 7.4905 },
    launchOptions: { args: ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"] },
  },
  webServer: {
    command: `sh scripts/e2e_server.sh ${PORT}`,
    url: `http://127.0.0.1:${PORT}/healthz`,
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
