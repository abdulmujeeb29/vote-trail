import { test, expect } from "@playwright/test";

test("demo replay plays all scenes with zero live API calls", async ({ page }) => {
  const calls = [];
  page.on("request", (r) => {
    const u = new URL(r.url());
    if ((u.pathname.startsWith("/api/") && u.pathname !== "/api/me/sync") || /openai|tavily|elevenlabs/.test(u.host)) calls.push(r.url());
  });
  await page.goto("/demo/");
  await expect(page.locator(".scene.on h1")).toContainText("Amaka");
  expect(await page.evaluate(() => window.__demoTotal)).toBeLessThanOrEqual(150);
  await page.evaluate(() => window.__demoSpeed(20));
  await page.click("#play");
  await page.waitForFunction(() => window.__demoDone === true, null, { timeout: 30000 });
  await expect(page.locator(".scene.on h1")).toContainText("Rules decide");
  expect(calls).toEqual([]);
});

test("result scene shows the mismatch and the PB difference", async ({ page }) => {
  await page.goto("/demo/");
  for (let i = 0; i < 4; i++) await page.click("#next");
  await expect(page.locator("tr[data-party='PB']")).toHaveClass(/diff/, { timeout: 15000 });
  await expect(page.locator("#result-card")).toBeVisible({ timeout: 15000 });
  await expect(page.locator("#result-card")).toContainText(/mismatch with irev/i);
  await page.click("#next");
  await expect(page.locator("#rumour-head")).toHaveText("We never confirm am", { timeout: 15000 });
});
