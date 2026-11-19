// Tiny CSS-3D helpers: cuboids on an isometric floor. No libraries, works offline.

// A cuboid w (x) by l (y) on the floor, h tall. Faces get .f-top/.f-front/... classes.
export function box(w, l, h, o = {}) {
  const b = document.createElement("div");
  b.className = `box ${o.cls || ""}`;
  Object.assign(b.style, { width: `${w}px`, height: `${l}px`, left: `${o.x ?? -w / 2}px`, top: `${o.y ?? -l / 2}px` });
  const face = (cls, css, html = "") => {
    const d = document.createElement("div");
    d.className = `face ${cls}`;
    Object.assign(d.style, css);
    if (html) d.innerHTML = html;
    b.append(d);
  };
  face("f-back", { width: `${w}px`, height: `${h}px`, left: 0, top: 0, transformOrigin: "top", transform: "rotateX(90deg)" });
  face("f-left", { width: `${h}px`, height: `${l}px`, left: `${-h}px`, top: 0, transformOrigin: "right", transform: "rotateY(90deg)" });
  face("f-right", { width: `${h}px`, height: `${l}px`, left: `${w}px`, top: 0, transformOrigin: "left", transform: "rotateY(-90deg)" });
  face("f-front", { width: `${w}px`, height: `${h}px`, left: 0, top: `${l - h}px`, transformOrigin: "bottom", transform: "rotateX(-90deg)" }, o.front);
  face("f-top", { width: `${w}px`, height: `${l}px`, left: 0, top: 0, transform: `translateZ(${h}px)`, borderRadius: o.radius ? `${o.radius}px` : "" }, o.top);
  return b;
}

export const el = (cls, html = "") => {
  const d = document.createElement("div");
  d.className = cls;
  if (html) d.innerHTML = html;
  return d;
};

// "Your polling unit" scene: a small school block with a floating pin.
document.querySelectorAll("[data-scene='unit']").forEach((iso) => {
  iso.append(el("floor"), el("floor-glow"));
  iso.append(box(130, 90, 70, { x: -65, y: -45 }), box(60, 60, 40, { x: 80, y: -10 }));
  iso.append(el("pin", "<i></i>"));
});
