// Builds the landing page's second figure with the Anatomy kit: a line of four agent stations joined by queue
// trays. On scroll the third station has crashed (lifted, red lamp) while its messages wait in the tray before it;
// a fresh station drops in and the messages move on. Writes src/components/landing/faultline-art.json.
//
//   node scripts/build-faultline.mjs [--preview]
import { writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import * as k from "../vendor/anatomy/iso-kit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const WIDTH = 760;
const HEIGHT = 440;
const BASE = { x: -176, y: -54, w: 352, d: 108, r: 6 };
const BASE_H = 8;
const STATIONS = [-126, -42, 42, 126]; // x of each agent station (Planner, Researcher, Writer, Critic)
const TRAYS = [-84, 0, 84]; // queue trays between stations
const ST = { w: 40, d: 54, h: 24 };
const LIFT = 46; // how high the crashed station floats
const CRASHED = 2;

const P = k.fitProjection(
  [...k.boxCorners(BASE, -BASE_H - 4, 0), [STATIONS[CRASHED] + ST.w / 2, 0, ST.h + LIFT + 6]],
  WIDTH, HEIGHT, { pad: 26, azimuth: 38, elevation: 30 },
);
const at = (p) => k.iso(p, P);
const S = (paths, style) => k.solidSvg(paths, style);
const L = (d, style) => k.lineSvg(d, style);
const D = (points, style) => k.dotsSvg(points, style);

function base() {
  const out = [`<path class="iso-halo" d="${k.haloOf(BASE, -BASE_H - 4, BASE_H, P)}"/>`];
  for (const [x, y] of k.corners(BASE, 14).sort((a, b) => k.depthOf([...a, 0], P) - k.depthOf([...b, 0], P))) {
    out.push(S(k.cylinder(x, y, 5, -BASE_H - 4, 4, P, 20), { tone: "lo" }));
  }
  out.push(S(k.slabOf(BASE, -BASE_H, BASE_H, P, 8, 1.2), { tone: "mid", inner: k.lineSvg(k.sideSeam(BASE, -BASE_H + 2.5, P, 8), { tone: "faint" }) }));
  out.push(L(k.planOutline(k.insetPlan(BASE, 6), 0, P), { tone: "faint" }));
  const screws = k.corners(BASE, 12);
  out.push(L(screws.map(([x, y]) => k.ring(x, y, 2.4, 0, P, 14)).join(""), { tone: "lo" }));
  out.push(D(screws.map(([x, y]) => at([x, y, 0])), { size: 0.5 }));
  // the lane every message travels along: two rails, end stops, a ruler strip with ticks
  for (const y of [-5, 3]) out.push(S(k.slabOf({ x: -164, y, w: 328, d: 2, r: 0.5 }, 0, 2, P, 2, 0.3), { tone: "lo" }));
  for (const x of [-168, 164]) out.push(S(k.slabOf({ x, y: -8, w: 4, d: 14, r: 1 }, 0, 5, P, 3, 0.4), { tone: "mid" }));
  const strip = { x: -150, y: BASE.y + BASE.d - 11, w: 300, d: 5, r: 1 };
  out.push(S(k.slabOf(strip, 0, 0.6, P, 3), { tone: "lo", crease: "none" }));
  const t = k.topTicks(strip.x + 3, strip.x + strip.w - 3, 5, 5, strip.y + 0.5, 0.6, [1.6, 3], P);
  out.push(L(t.minor, { tone: "lo" }), L(t.major, { tone: "mid" }));
  // queue trays: a shallow well with a lip, where messages wait for the next station
  for (const x of TRAYS) {
    const tray = { x: x - 14, y: -16, w: 28, d: 32, r: 2 };
    out.push(S(k.slabOf(tray, 0, 4, P, 4, 0.4), { tone: "mid" }));
    out.push(S(k.slabOf(k.insetPlan(tray, 2.5), 1.5, 2.5, P, 4), { tone: "lo", crease: "none" }));
    out.push(D([at([tray.x + 2, tray.y + 2, 4]), at([tray.x + tray.w - 2, tray.y + tray.d - 2, 4])], { size: 0.4 }));
  }
  return out.join("");
}

function station(x, { lit = false, crashed = false } = {}) {
  const plan = { x: x - ST.w / 2, y: -ST.d / 2 - 6, w: ST.w, d: ST.d, r: 3 };
  const out = [S(k.slabOf(plan, 0, ST.h, P, 4, 0.9), { tone: lit ? "hi" : "mid", crease: "lo", lit, inner: k.lineSvg(k.sideSeam(plan, 7, P, 4), { tone: "faint" }) })];
  out.push(L(k.planOutline(k.insetPlan(plan, 3.5), ST.h, P, 3), { tone: "faint" }));
  for (let v = 0; v < 4; v++) {
    const y = plan.y + 9 + v * 5;
    out.push(L(k.onTop([[plan.x + 7, y], [plan.x + plan.w - 15, y], [plan.x + plan.w - 15, y + 2], [plan.x + 7, y + 2]], ST.h, P, true), { tone: "lo" }));
  }
  const lamp = [plan.x + plan.w - 8, plan.y + 12];
  out.push(S(k.cylinder(lamp[0], lamp[1], 3, ST.h, 1.2, P, 18), { tone: "mid" }));
  // two lamp heads: the page shows the red one while the station is down, the lit one once it's back
  out.push(`<g data-lamp="ok">${S(k.cylinder(lamp[0], lamp[1], 2, ST.h + 1.2, 1.6, P, 18), { tone: "hi", lit: true })}</g>`);
  if (crashed) out.push(`<g data-lamp="down" style="opacity:0">${L(k.ring(lamp[0], lamp[1], 2, ST.h + 2.8, P, 18), { tone: "red" })}${D([at([lamp[0], lamp[1], ST.h + 2.8])], { size: 1.6, tone: "mid" })}</g>`);
  const knob = [plan.x + plan.w - 9, plan.y + plan.d - 11];
  out.push(S(k.cylinder(knob[0], knob[1], 4, ST.h, 3.2, P, 24, 0.4), { tone: "mid" }));
  out.push(L(k.knurl(knob[0], knob[1], 4, ST.h, ST.h + 3.2, 22, P), { tone: "lo" }));
  out.push(D([[plan.x + 4, plan.y + 4], [plan.x + 4, plan.y + plan.d - 4]].map(([px, py]) => at([px, py, ST.h])), { size: 0.45 }));
  return out.join("");
}

function capsule(x) {
  const cap = { x: x - 7, y: -4.5, w: 14, d: 7, r: 3.4 };
  return S(k.slabOf(cap, 2, 5.5, P, 6, 0.5), { tone: "hi", crease: "lo" }) + L(k.lineOnTop([x - 2, -3], [x - 2, 2], 7.5, P), { tone: "lo" });
}

// paint order: base, the stations behind the queue, the waiting messages, the crashed station, the rest
const stations = STATIONS.map((x, i) => (i === CRASHED ? "" : `<g data-station="${i}">${station(x)}</g>`));
const crashed = station(STATIONS[CRASHED], { crashed: true });
const caps = [-8, 0, 8].map((dx) => capsule(TRAYS[1] + dx)); // three messages waiting in the tray, back to front

const unit = (v) => { const a = at([0, 0, 0]); const b = at(v); return [b[0] - a[0], b[1] - a[1]]; };
const out = {
  width: WIDTH, height: HEIGHT, lift: LIFT, travel: TRAYS[2] - TRAYS[1],
  xUnit: unit([1, 0, 0]), zUnit: unit([0, 0, 1]),
  base: base(), stationsBefore: stations.slice(0, CRASHED).join(""), stationsAfter: stations.slice(CRASHED + 1).join(""),
  crashed, capsules: caps,
};
writeFileSync(join(HERE, "../src/components/landing/faultline-art.json"), JSON.stringify(out));
console.log("wrote faultline-art.json:", JSON.stringify(out).length, "chars");

if (process.argv.includes("--preview")) {
  const body = [out.base, out.stationsBefore, ...caps, `<g transform="${k.translateAlong(P, [0, 0, LIFT])}">${crashed}</g>`, out.stationsAfter].join("");
  writeFileSync(join(HERE, "../.faultline-preview.html"), k.pageHtml({ title: "faultline", theme: "dark", body: k.figureSvg({ width: WIDTH, height: HEIGHT, label: "preview", body: [body] }), width: 820 }));
  console.log("wrote .faultline-preview.html");
}
