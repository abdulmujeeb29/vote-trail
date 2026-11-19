import { test, expect } from "@playwright/test";

test("basic phone: dial USSD, learn the PU moved, then SMS commands work", async ({ page }) => {
  await page.goto("/simulator/");
  await page.fill("#sim-phone", "08035551234");
  const input = page.locator("#sim-input");
  const display = page.locator("#sim-display");

  await input.fill("*384*2027#"); await page.click("#sim-send");
  await expect(display).toContainText("1 My polling unit");
  await input.fill("1"); await page.click("#sim-send");
  await expect(display).toContainText("PU code");
  await input.fill("370602002"); await page.click("#sim-send");
  await expect(display).toContainText("MOVED");
  await expect(display).toContainText("37/06/02/004");

  const send = async (text, expectText) => {
    await expect(page.locator("#sim-send")).toBeEnabled();
    await input.fill(text); await page.click("#sim-send");
    await expect(display).toContainText(expectText);
  };
  await send("*384*2027#", "1 My polling unit");
  await send("5", "1 English");
  await send("2", "Pidgin");

  await page.fill("#sms-text", "PU 370602002");
  await page.click("text=Send SMS");
  await expect(page.locator("#inbox")).toContainText("MOVED", { timeout: 10000 });
});
