// Offline upload queue. Storage is pluggable so it can be unit-tested in Node.
// States: saved -> uploading -> received -> checking -> result

export const STATES = ["saved", "uploading", "received", "checking", "result"];

export function memoryStore() {
  const items = new Map();
  return {
    async all() { return [...items.values()].sort((a, b) => a.createdAt - b.createdAt); },
    async put(item) { items.set(item.key, structuredClone(item)); },
    async get(key) { const v = items.get(key); return v ? structuredClone(v) : undefined; },
    async delete(key) { items.delete(key); },
  };
}

export function indexedDbStore(name = "votetrail", store = "uploads") {
  const open = () => new Promise((resolve, reject) => {
    const req = indexedDB.open(name, 1);
    req.onupgradeneeded = () => req.result.createObjectStore(store, { keyPath: "key" });
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
  const run = async (mode, fn) => {
    const db = await open();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(store, mode);
      const req = fn(tx.objectStore(store));
      tx.oncomplete = () => resolve(req && req.result);
      tx.onerror = () => reject(tx.error);
    });
  };
  return {
    async all() { return ((await run("readonly", (s) => s.getAll())) || []).sort((a, b) => a.createdAt - b.createdAt); },
    async put(item) { await run("readwrite", (s) => s.put(item)); },
    async get(key) { return run("readonly", (s) => s.get(key)); },
    async delete(key) { await run("readwrite", (s) => s.delete(key)); },
  };
}

export function newKey() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID().replace(/-/g, "");
  return Array.from({ length: 32 }, () => Math.floor(Math.random() * 16).toString(16)).join("");
}

export class UploadQueue {
  constructor({ store, send, now = () => Date.now() }) {
    this.store = store; this.send = send; this.now = now; this.flushing = null;
  }

  async add({ blob, fields }) {
    const item = { key: newKey(), fields, blob, state: "saved", attempts: 0, createdAt: this.now(), error: "" };
    await this.store.put(item);
    return item;
  }

  async list() { return this.store.all(); }

  // Sends every pending item once. Concurrent calls share one run (no double sends).
  flush() {
    if (!this.flushing) {
      this.flushing = this._flush().finally(() => { this.flushing = null; });
    }
    return this.flushing;
  }

  async _flush() {
    const results = [];
    for (const item of await this.store.all()) {
      if (item.state !== "saved" && item.state !== "uploading") continue;
      item.state = "uploading"; item.attempts += 1;
      await this.store.put(item);
      try {
        const res = await this.send(item);
        if (res.ok || res.status === 200 || res.status === 201) {
          item.state = "received"; item.error = ""; item.statusUrl = res.body?.status_url || "";
          item.blob = null;
        } else if (res.status >= 400 && res.status < 500 && res.status !== 429) {
          item.state = "failed"; item.error = res.body?.error || "Rejected";
        } else {
          item.state = "saved"; item.error = "Will retry";
        }
      } catch (err) {
        item.state = "saved"; item.error = "Offline. Will retry.";
      }
      await this.store.put(item);
      results.push(item);
    }
    return results;
  }

  async markResult(key, state, result) {
    const item = await this.store.get(key);
    if (!item) return;
    item.state = state; item.result = result;
    await this.store.put(item);
  }
}
