import { UploadQueue, indexedDbStore, newKey } from "./offline-queue.js";

const $ = (id) => document.getElementById(id);
const form = $("capture-form");
const video = $("camera");
const canvas = $("shot");
const errorBox = $("form-error");
let photo = null; // Blob
let stream = null;

function deviceId() {
  try {
    let id = localStorage.getItem("vt_device");
    if (!id) { id = newKey(); localStorage.setItem("vt_device", id); }
    return id;
  } catch { return ""; }
}

function csrf() {
  const m = document.cookie.match(/csrftoken=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : "";
}

async function send(item) {
  const fd = new FormData();
  for (const [k, v] of Object.entries(item.fields)) fd.append(k, v ?? "");
  fd.append("idempotency_key", item.key);
  fd.append("image", item.blob, "ec8a.jpg");
  const res = await fetch("/api/results/uploads", { method: "POST", body: fd, headers: { "X-CSRFToken": csrf() }, credentials: "same-origin" });
  let body = {};
  try { body = await res.json(); } catch { /* ignore */ }
  return { ok: res.ok, status: res.status, body };
}

const queue = new UploadQueue({ store: indexedDbStore(), send });
const LABELS = { saved: "Saved on phone", uploading: "Uploading…", received: "Received", checking: "Checking", result: "Result ready", failed: "Not accepted" };

async function render() {
  const items = await queue.list();
  const list = $("queue-list");
  if (!items.length) return;
  list.innerHTML = "";
  for (const it of items.reverse()) {
    const li = document.createElement("li");
    li.dataset.on = "";
    const pu = it.fields.pu_code;
    const status = it.result ? ` · ${it.result.label}` : "";
    li.textContent = `PU ${pu} · ${LABELS[it.state] || it.state}${status}${it.error && it.state !== "received" ? " · " + it.error : ""}`;
    if (it.state === "result") {
      const a = document.createElement("a");
      a.href = `/pu/${pu.replace(/\//g, "-")}/result/`; a.textContent = " View";
      li.append(a);
    }
    list.append(li);
  }
}

async function poll() {
  for (const it of await queue.list()) {
    if (!it.statusUrl || it.state === "result" || it.state === "failed") continue;
    try {
      const r = await fetch(it.statusUrl, { credentials: "same-origin" });
      if (!r.ok) continue;
      const data = await r.json();
      if (data.state === "checked" || data.state === "rejected") {
        await queue.markResult(it.key, "result", data.result);
      } else {
        await queue.markResult(it.key, "checking", null);
      }
    } catch { /* offline */ }
  }
  render();
}

async function compress(source, w, h) {
  const max = 2000;
  const scale = Math.min(1, max / Math.max(w, h));
  canvas.width = Math.round(w * scale); canvas.height = Math.round(h * scale);
  canvas.getContext("2d").drawImage(source, 0, 0, canvas.width, canvas.height);
  canvas.hidden = false; video.hidden = true;
  return new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.8));
}

$("start-camera").addEventListener("click", async () => {
  try {
    stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" }, audio: false });
    video.srcObject = stream; await video.play();
    $("take-photo").hidden = false; $("start-camera").hidden = true;
  } catch {
    $("fallback-label").hidden = false; $("start-camera").hidden = true;
  }
});

function videoReady() {
  if (video.videoWidth > 0) return Promise.resolve();
  return new Promise((resolve) => video.addEventListener("loadeddata", resolve, { once: true }));
}

$("take-photo").addEventListener("click", async () => {
  await videoReady();
  photo = await compress(video, video.videoWidth, video.videoHeight);
  if (!photo) { errorBox.textContent = "The camera isn't ready. Try again."; errorBox.hidden = false; return; }
  form.dataset.inApp = "1";
  stream?.getTracks().forEach((t) => t.stop());
  $("take-photo").hidden = true; $("save").disabled = false;
});

$("fallback-input").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const bmp = await createImageBitmap(file);
  photo = await compress(bmp, bmp.width, bmp.height);
  form.dataset.inApp = "1"; // capture="environment" opens the camera directly
  $("save").disabled = false;
});

function where() {
  return new Promise((resolve) => {
    if (!navigator.geolocation) return resolve({});
    navigator.geolocation.getCurrentPosition(
      (p) => resolve({ lat: p.coords.latitude.toFixed(6), lng: p.coords.longitude.toFixed(6) }),
      () => resolve({}), { timeout: 4000, maximumAge: 60000 });
  });
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  errorBox.hidden = true;
  const pu = $("pu_code").value.trim();
  if (!/^\d{1,2}[/-]\d{1,2}[/-]\d{1,2}[/-]\d{1,3}$/.test(pu)) {
    errorBox.textContent = "Enter the polling unit code, like 37/06/02/004."; errorBox.hidden = false; return;
  }
  if (!photo) { errorBox.textContent = "Take a photo first."; errorBox.hidden = false; return; }
  $("save").disabled = true;
  const loc = await where();
  await queue.add({ blob: photo, fields: {
    pu_code: pu, election: form.election.value, in_app: form.dataset.inApp || "0",
    captured_at: new Date().toISOString(), device_id: deviceId(), ...loc } });
  photo = null; await render(); await queue.flush(); await render();
});

window.addEventListener("online", () => queue.flush().then(render));
render(); queue.flush().then(render);
setInterval(poll, 4000);
