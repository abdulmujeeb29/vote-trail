import { test, expect } from "@playwright/test";

test("result-sheet photo taken offline survives reload and syncs once when back online", async ({ page, context }) => {
  await page.goto("/capture/37-06-02-004/");
  await page.waitForFunction(() => navigator.serviceWorker && navigator.serviceWorker.controller !== null, null, { timeout: 15000 }).catch(() => {});
  await page.reload();
  await expect(page.locator("#pu_code")).toHaveValue("37/06/02/004");

  await context.setOffline(true);
  await page.getByRole("button", { name: "Open camera" }).click();
  await page.getByRole("button", { name: "Take photo" }).click();
  await page.getByRole("button", { name: "Save and send" }).click();
  await expect(page.locator("#queue-list")).toContainText("Saved on phone", { timeout: 15000 });

  await page.reload(); // still offline: page comes from the service worker, item from IndexedDB
  await expect(page.locator("#queue-list")).toContainText("Saved on phone", { timeout: 15000 });

  await context.setOffline(false);
  await page.evaluate(() => window.dispatchEvent(new Event("online")));
  await expect(page.locator("#queue-list")).toContainText(/Received|Checking|Result ready/, { timeout: 20000 });
  await expect(page.locator("#queue-list")).toContainText("Result ready", { timeout: 30000 });

  const res = await page.request.get("/api/pu/37-06-02-004/result");
  expect((await res.json()).result.status).not.toBe("pending");
  await expect(page.locator("#queue-list li")).toHaveCount(1);
});
