import { test, expect } from "@playwright/test";

test("first run: 3-tap setup with location, then My vote shows the move and one next action", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Every vote, every voice/ })).toBeVisible();
  await page.getByRole("link", { name: /Get started/ }).first().click();
  await expect(page).toHaveURL(/\/setup\//);
  await expect(page.locator(".appnav")).toHaveCount(0);
  await page.getByText("Naijá (Pidgin)").click();
  await page.getByRole("button", { name: /Continue/ }).click();
  await page.getByRole("button", { name: /Use my location/ }).click();
  await expect(page.locator("#near .choice").first()).toContainText("37/06/02/004", { timeout: 10000 });
  await page.fill("#pu_code", "37/06/02/002");
  await page.getByRole("button", { name: /Na my unit be this/ }).click();
  await page.fill("#phone", "0803 222 1111");
  await page.getByRole("button", { name: /Finish/ }).click();
  await expect(page.getByText("Ready", { exact: true })).toBeVisible();
  await page.getByRole("link", { name: /Open my vote/ }).click();

  // She chose Pidgin at step 1, so the app is now in Pidgin.
  await expect(page.getByRole("alert")).toContainText("Your polling unit don move");
  await expect(page.locator(".panel.next")).toContainText("Go see your new polling unit");
  await expect(page.locator("#sync-text")).toHaveText(/SYNCED|CHECKING/);
  await page.locator(".panel.next").getByRole("button", { name: /Done/ }).click();
  await expect(page.locator(".panel.next")).toContainText("Make sure say you don register");

  await page.getByRole("link", { name: "Check am", exact: true }).click();
  await expect(page.getByText("from your profile")).toBeVisible();
  await expect(page.locator("main")).toContainText("37/06/02/004");

  await page.getByRole("link", { name: "Wetin happen", exact: true }).click();
  await expect(page.locator(".feed")).toContainText("We don send alert to your phone");
});

test("detail pages: back bar returns, and marking PVC updates My vote", async ({ page }) => {
  await page.goto("/vote/?skip=1");
  await page.goto("/pvc/");
  await page.getByRole("button", { name: /I have my PVC/ }).click();
  await expect(page.getByRole("button", { name: /PVC collected · undo/ })).toBeVisible();
  await page.locator(".backbar a").click();
  await expect(page.locator(".idcard")).toContainText(/PVC collected/i);
});

test("rumour check from Verify lands on a live verdict page", async ({ page }) => {
  await page.goto("/verify/?tab=rumour");
  await page.fill("#text", "Officials have not arrived at Garki ward 5 polling unit since morning");
  await page.selectOption("#category", "late_officials");
  await page.getByRole("button", { name: /Check it/ }).click();
  await expect(page).toHaveURL(/\/rumours\/\d+\//);
  await expect(page.locator(".decrypt")).toBeVisible();
  await page.locator(".backbar a").click();
  await expect(page).toHaveURL(/\/verify\/\?tab=rumour/);
});

test("find by location lists the nearest units", async ({ page }) => {
  await page.goto("/find/");
  await page.getByRole("button", { name: /Use my location/ }).click();
  await expect(page.locator("#nearby-list li").first()).toContainText("37/06/02/004", { timeout: 10000 });
});

test("capture page fills the polling unit from location", async ({ page }) => {
  await page.goto("/capture/");
  await page.getByRole("button", { name: /Fill from my location/ }).click();
  await expect(page.locator("#pu_code")).toHaveValue("37/06/02/004", { timeout: 10000 });
});

test("landing: watch the demo and come back, or just look around", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: /Watch the full replay/ }).click();
  await expect(page).toHaveURL(/\/demo\//);
  await page.locator(".backbar a").click();
  await page.getByRole("link", { name: "Just look around" }).click();
  await expect(page.locator(".panel.next")).toBeVisible();
  await expect(page.locator(".appnav")).toBeVisible();
  // The landing page is always at / and links back into the app.
  await page.locator(".brand").click();
  await expect(page.getByRole("heading", { name: /Every vote, every voice/ })).toBeVisible();
  await page.getByRole("link", { name: /Open my vote/ }).first().click();
  await expect(page.locator(".panel.next")).toBeVisible();
});
