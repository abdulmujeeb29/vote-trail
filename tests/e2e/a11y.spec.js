import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const pages = ["/", "/vote/?skip=1", "/setup/", "/setup/?step=2", "/setup/?step=3", "/verify/", "/verify/?tab=rumour",
  "/activity/", "/ask/", "/register/", "/pvc/", "/accessibility/", "/find/?q=garki",
  "/pu/37-06-02-002/", "/pu/37-06-02-004/today/", "/pu/37-06-02-004/result/", "/capture/",
  "/simulator/", "/demo/", "/dashboard/login/"];

for (const path of pages) {
  test(`no serious accessibility violations: ${path}`, async ({ page }) => {
    await page.goto(path);
    const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
    const bad = results.violations.filter((v) => ["serious", "critical"].includes(v.impact));
    expect(bad.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).slice(0, 3).join(", ")}`)).toEqual([]);
  });
}
