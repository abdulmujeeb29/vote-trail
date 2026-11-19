import { test } from "node:test";
import assert from "node:assert/strict";
import { UploadQueue, memoryStore } from "../../static/js/offline-queue.js";

const blob = new Blob(["x"]);
const fields = { pu_code: "37/06/02/004" };

test("saved items survive a 'reload' (same store, new queue)", async () => {
  const store = memoryStore();
  const q1 = new UploadQueue({ store, send: async () => { throw new Error("offline"); } });
  await q1.add({ blob, fields });
  await q1.flush();
  const q2 = new UploadQueue({ store, send: async () => ({ ok: true, status: 201, body: {} }) });
  const items = await q2.list();
  assert.equal(items.length, 1);
  assert.equal(items[0].state, "saved");
  assert.equal(items[0].error, "Offline. Will retry.");
});

test("offline then online sends exactly once, with the same key", async () => {
  const store = memoryStore();
  let online = false; const sent = [];
  const q = new UploadQueue({ store, send: async (it) => { if (!online) throw new Error("offline"); sent.push(it.key); return { ok: true, status: 201, body: { status_url: "/s" } }; } });
  const item = await q.add({ blob, fields });
  await q.flush(); assert.equal(sent.length, 0);
  online = true;
  await Promise.all([q.flush(), q.flush(), q.flush()]);
  await q.flush();
  assert.deepEqual(sent, [item.key]);
  const [stored] = await q.list();
  assert.equal(stored.state, "received");
  assert.equal(stored.blob, null);
  assert.equal(stored.statusUrl, "/s");
});

test("server rejection stops retries; 5xx and 429 retry", async () => {
  const store = memoryStore();
  const replies = [{ ok: false, status: 503 }, { ok: false, status: 429 }, { ok: false, status: 400, body: { error: "Bad photo" } }];
  let calls = 0;
  const q = new UploadQueue({ store, send: async () => replies[calls++] });
  await q.add({ blob, fields });
  await q.flush(); assert.equal((await q.list())[0].state, "saved");
  await q.flush(); assert.equal((await q.list())[0].state, "saved");
  await q.flush();
  const [it] = await q.list();
  assert.equal(it.state, "failed"); assert.equal(it.error, "Bad photo"); assert.equal(it.attempts, 3);
  await q.flush(); assert.equal(calls, 3);
});

test("markResult updates state", async () => {
  const store = memoryStore();
  const q = new UploadQueue({ store, send: async () => ({ ok: true, status: 201, body: {} }) });
  const it = await q.add({ blob, fields });
  await q.markResult(it.key, "result", { label: "Matches IReV" });
  assert.equal((await q.list())[0].result.label, "Matches IReV");
  await q.markResult("missing", "result", {});
});
