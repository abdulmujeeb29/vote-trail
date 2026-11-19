import { test, expect } from "@playwright/test";

// Live: browser ↔ Azure gpt-realtime over WebRTC, with the tool loop. Run with LIVE=1.
test("voice assistant connects to gpt-realtime and answers from tools", async ({ page, context }) => {
  test.skip(!process.env.LIVE, "Set LIVE=1 to run against Azure.");
  await context.grantPermissions(["microphone"]);
  await page.goto("/ask/");
  await page.click("#orb");
  await page.waitForFunction(() => window.__voiceReady === true, null, { timeout: 30000 });
  await expect(page.locator("#orb")).toHaveAttribute("aria-pressed", "true");

  const ask = (text) => page.evaluate((t) => {
    window.__voiceDc.send(JSON.stringify({ type: "conversation.item.create", item: { type: "message",
      role: "user", content: [{ type: "input_text", text: t }] } }));
    window.__voiceDc.send(JSON.stringify({ type: "response.create" }));
  }, text);
  const debug = async () => console.log("EVENTS:", await page.evaluate(() => [...new Set(window.__events || [])].join(",")),
    "\nANSWERS:", await page.evaluate(() => JSON.stringify(window.__answers || [])),
    "\nTOOLS:", await page.evaluate(() => JSON.stringify((window.__toolCalls || []).map((t) => t.name))));

  await ask("Where is polling unit 37/06/02/002? I want to know where to vote.");
  // The assistant is told to read codes back before using them; confirm if it asks.
  for (let turn = 0; turn < 3; turn++) {
    const used = await page.waitForFunction(() => (window.__toolCalls || []).some((c) => c.name === "lookup_pu"),
      null, { timeout: 20000 }).then(() => true).catch(() => false);
    if (used) break;
    await ask("Yes, that is correct.");
  }
  try {
    await page.waitForFunction(() => (window.__answers || []).join(" ").match(/004|New Pri|moved|move/i), null, { timeout: 45000 });
  } catch (err) { await debug(); throw err; }
  const answers = await page.evaluate(() => window.__answers.join(" | "));
  console.log("ASSISTANT:", answers);
  expect(answers.toLowerCase()).not.toMatch(/\bwon\b|winner/);
  await page.click("#orb");
  await expect(page.locator("#orb-status")).toHaveText("Tap to talk");
});
