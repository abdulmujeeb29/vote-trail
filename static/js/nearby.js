// "Use my location": find the nearest polling units without typing a code.
export function locate() {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) return reject(new Error("Location isn't available on this phone."));
    navigator.geolocation.getCurrentPosition(
      (p) => resolve({ lat: p.coords.latitude, lng: p.coords.longitude }),
      () => reject(new Error("Allow location, or type your code instead.")),
      { timeout: 8000, maximumAge: 60000, enableHighAccuracy: true });
  });
}

export async function nearest() {
  const { lat, lng } = await locate();
  const res = await fetch(`/api/pu/nearest?lat=${lat}&lng=${lng}`, { credentials: "same-origin" });
  return (await res.json()).results || [];
}

const fmt = (m) => (m < 1000 ? `${m} m` : `${(m / 1000).toFixed(1)} km`);

document.querySelectorAll("[data-nearby]").forEach((btn) => {
  const out = document.getElementById(btn.dataset.nearby);
  const mode = btn.dataset.mode || "links";
  btn.addEventListener("click", async () => {
    btn.disabled = true; const label = btn.textContent; btn.textContent = "Finding you…";
    try {
      const list = await nearest();
      out.innerHTML = "";
      if (mode === "pick") {
        const input = document.getElementById("pu_code");
        for (const pu of list.slice(0, 3)) {
          const b = document.createElement("button");
          b.type = "button"; b.className = "choice";
          b.innerHTML = '<span class="dot"></span><span><span class="mono"></span><br><span class="mute"></span></span>';
          b.querySelector(".mono").textContent = pu.code;
          b.querySelector(".mute").textContent = `${pu.name} · ${fmt(pu.distance_m)}`;
          b.addEventListener("click", () => { out.querySelectorAll(".choice").forEach((c) => c.setAttribute("aria-pressed", "false")); b.setAttribute("aria-pressed", "true"); input.value = pu.code; });
          out.append(b);
        }
        if (list[0]) { out.firstChild.setAttribute("aria-pressed", "true"); input.value = list[0].code; }
      } else if (mode === "fill") {
        const input = document.getElementById(btn.dataset.target);
        if (list[0]) { input.value = list[0].code; input.dispatchEvent(new Event("change")); }
        out.textContent = list[0] ? `Nearest: ${list[0].name} (${fmt(list[0].distance_m)} away). Change it if this isn't your unit.` : "No polling unit found nearby.";
      } else {
        for (const pu of list) {
          const li = document.createElement("li");
          const a = document.createElement("a"); a.href = pu.url;
          a.innerHTML = `<span class="mono"></span> · <span></span>`;
          a.children[0].textContent = pu.code; a.children[1].textContent = pu.name;
          const tag = document.createElement("span"); tag.className = "tag"; tag.textContent = `${fmt(pu.distance_m)}${pu.moved ? " · moved" : ""}`;
          li.append(a, " ", tag); out.append(li);
        }
      }
    } catch (e) { out.textContent = e.message; }
    finally { btn.disabled = false; btn.textContent = label; }
  });
});

// Setup: the confirm button becomes the primary action once a unit is chosen or typed.
const confirmBtn = document.getElementById("confirm-unit");
const codeInput = document.getElementById("pu_code");
if (confirmBtn && codeInput) {
  const sync = () => confirmBtn.classList.toggle("go", codeInput.value.trim().length >= 7);
  codeInput.addEventListener("input", sync);
  codeInput.addEventListener("change", sync);
  new MutationObserver(sync).observe(document.getElementById("near") || document.body, { childList: true, subtree: true, attributes: true });
  sync();
}
