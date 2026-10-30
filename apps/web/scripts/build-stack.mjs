// Builds the landing page's isometric figure with the Anatomy kit (vendor/anatomy, MIT):
// an exploded four-tier rack that is the scheduler itself. Writes src/components/landing/stack-art.json
// (static SVG per tier + where each callout points) and, with --preview, a standalone page to look at.
//
//   node scripts/build-stack.mjs [--preview]
//
// Tiers, bottom to top:
//   record   the run document: a cabinet of drawers (one pulled out: this run) and a red dead-letter tray
//   actors   four worker modules (Planner, Researcher, Writer, Critic), each with a status lamp
//   queues   four channels, one per agent; capsules carry only a run id; a gauge shows the 429 pause
//   console  where the request comes in: a screen with the prompt and a keyboard
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import * as k from "../vendor/anatomy/iso-kit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const WIDTH = 560;
const HEIGHT = 760;

const PLATE = { x: -112, y: -78, w: 224, d: 156, r: 6 };
const PLATE_H = 7;
const POST_H = 22; // standoffs under each plate; assembled, they rest on the tier below
const GAP_SHUT = PLATE_H + POST_H + 26; // tier pitch when assembled (tallest content is 26)
const GAP_OPEN = 128; // tier pitch fully exploded
const TIER_IDS = ["record", "actors", "queues", "console"];

const P = k.fitProjection(
  [...k.boxCorners(PLATE, -PLATE_H - POST_H, 0), ...k.boxCorners(PLATE, 3 * GAP_OPEN - PLATE_H, 3 * GAP_OPEN + 30)],
  WIDTH,
  HEIGHT,
  { pad: 28, azimuth: 45, elevation: 30 },
);

const at = (p) => k.iso(p, P);
const S = (paths, style) => k.solidSvg(paths, style);
const L = (d, style) => k.lineSvg(d, style);
const D = (points, style) => k.dotsSvg(points, style);
const depth = (x, y, z = 0) => k.depthOf([x, y, z], P);
/** Paint items back to front: [{ at: [x, y, z], svg }] */
const painted = (items) => items.sort((a, b) => depth(...a.at) - depth(...b.at)).map((i) => i.svg).join("");

// ---------- shared: the plate every tier sits on ----------
function plate(label) {
  const out = [`<path class="iso-halo" d="${k.haloOf(PLATE, -PLATE_H - POST_H, PLATE_H, P)}"/>`];
  const posts = k.corners(PLATE, 12).sort((a, b) => depth(...a) - depth(...b));
  for (const [x, y] of posts) {
    out.push(S(k.cylinder(x, y, 4.2, -PLATE_H - POST_H, POST_H, P, 24), { tone: "mid", crease: "none" }));
    out.push(L(k.sideArc(x, y, 4.2, -PLATE_H - POST_H + 4, P, 14), { tone: "faint" }));
  }
  out.push(S(k.slabOf(PLATE, -PLATE_H, PLATE_H, P, 8, 1.2), { tone: "mid", inner: k.lineSvg(k.sideSeam(PLATE, -PLATE_H + 2.4, P, 8), { tone: "faint" }) }));
  out.push(L(k.planOutline(k.insetPlan(PLATE, 6), 0, P), { tone: "faint" }));
  const screws = k.corners(PLATE, 12);
  out.push(L(screws.map(([x, y]) => k.ring(x, y, 2.6, 0, P, 16)).join(""), { tone: "lo" }));
  out.push(D(screws.map(([x, y]) => at([x, y, 0])), { size: 0.55 }));
  // front ruler strip with ticks, and a label plate with its engraved name
  const strip = { x: PLATE.x + 24, y: PLATE.y + PLATE.d - 12, w: 120, d: 6, r: 1 };
  out.push(S(k.slabOf(strip, 0, 0.6, P, 3), { tone: "lo", crease: "none" }));
  const t = k.topTicks(strip.x + 3, strip.x + strip.w - 3, 4, 5, strip.y + 0.6, 0.6, [1.8, 3.4], P);
  out.push(L(t.minor, { tone: "lo" }), L(t.major, { tone: "mid" }));
  const tag = { x: PLATE.x + PLATE.w - 58, y: PLATE.y + PLATE.d - 14, w: 44, d: 9, r: 1 };
  out.push(S(k.slabOf(tag, 0, 0.8, P, 3, 0.3), { tone: "mid", crease: "none" }));
  out.push(k.faceTextSvg(k.topMatrix([tag.x + tag.w / 2, tag.y + 6], 0.8, P, "x"), label, { size: 4.2, tone: "mid", anchor: "middle" }));
  out.push(D([at([tag.x + 3, tag.y + 4.5, 0.8]), at([tag.x + tag.w - 3, tag.y + 4.5, 0.8])], { size: 0.4 }));
  return out.join("");
}

// ---------- tier 1: the record (Mongo run documents + dead-letter tray) ----------
function record() {
  const items = [];
  const cab = (x0, pulled) => {
    const plan = { x: x0, y: -58, w: 56, d: 70, r: 2 };
    const H = 26;
    const out = [S(k.slabOf(plan, 0, H, P, 4, 0.8), { tone: "mid" })];
    out.push(L(k.planOutline(k.insetPlan(plan, 4), H, P, 3), { tone: "faint" }));
    out.push(D([[plan.x + 4, plan.y + 4], [plan.x + plan.w - 4, plan.y + 4], [plan.x + 4, plan.y + plan.d - 4], [plan.x + plan.w - 4, plan.y + plan.d - 4]].map(([x, y]) => at([x, y, H])), { size: 0.45 }));
    // three drawers on the front (+y) face; a drawer front is a thin slab standing proud of the face
    [0, 1, 2].forEach((i) => {
      const z = 1.5 + i * 8;
      const pull = pulled && i === 1 ? 22 : 0; // this run's document, pulled out
      const front = { x: plan.x + 3, y: plan.y + plan.d + pull, w: plan.w - 6, d: 2.2, r: 0.6 };
      if (pull) {
        const body = { x: plan.x + 5, y: plan.y + plan.d - 2, w: plan.w - 10, d: pull + 2, r: 0.8 };
        out.push(S(k.slabOf(body, z + 0.6, 5.4, P, 2, 0.4), { tone: "hi", crease: "lo", lit: true }));
        // the document's fields as printed rule lines (their ends are free by design)
        [0.3, 0.55, 0.8].forEach((f) => out.push(L(k.lineOnTop([body.x + 5, body.y + body.d * f], [body.x + body.w - 12, body.y + body.d * f], z + 6, P), { tone: "mid", free: true })));
      }
      out.push(S(k.slabOf(front, z, 6.4, P, 2, 0.3), { tone: pull ? "hi" : "mid", crease: "none", lit: !!pull }));
      const hx = front.x + front.w / 2;
      out.push(S(k.slabOf({ x: hx - 6, y: front.y + front.d, w: 12, d: 1.4, r: 0.6 }, z + 2.4, 1.6, P, 2), { tone: "mid", crease: "none" }));
    });
    return { at: [plan.x + plan.w / 2, plan.y + plan.d / 2, 0], svg: out.join("") };
  };
  items.push(cab(-96, false), cab(-34, true));
  // the dead-letter tray: an open tray holding a capsule that ran out of attempts
  const tray = { x: 38, y: -40, w: 58, d: 46, r: 3 };
  const tOut = [S(k.slabOf(tray, 0, 8, P, 5, 0.6), { tone: "mid" })];
  tOut.push(S(k.slabOf(k.insetPlan(tray, 3), 4, 4, P, 5), { tone: "lo", crease: "none" }));
  tOut.push(L(k.planOutline(k.insetPlan(tray, 3), 8, P, 5), { tone: "red" }));
  const cap = { x: tray.x + 12, y: tray.y + 16, w: 26, d: 9, r: 4.4 };
  tOut.push(S(k.slabOf(cap, 4, 7, P, 6, 0.5), { tone: "hi", crease: "lo" }));
  tOut.push(L(k.lineOnTop([cap.x + 9, cap.y + 1], [cap.x + 9, cap.y + cap.d - 1], 11, P), { tone: "red" }));
  tOut.push(k.faceTextSvg(k.topMatrix([tray.x + tray.w / 2, tray.y + tray.d - 0.5], 8, P, "x"), "DLQ", { size: 3.6, tone: "mid", anchor: "middle" }));
  items.push({ at: [tray.x + tray.w / 2, tray.y + tray.d / 2, 0], svg: tOut.join("") });
  // the replay lever beside the tray
  const lever = [tray.x + tray.w - 6, tray.y + tray.d + 12];
  items.push({ at: [...lever, 0], svg: [
    S(k.slabOf({ x: lever[0] - 7, y: lever[1] - 4, w: 14, d: 8, r: 1.5 }, 0, 3, P, 3, 0.4), { tone: "mid" }),
    S(k.cylinder(lever[0], lever[1], 1.3, 3, 14, P, 12), { tone: "mid", crease: "none" }),
    S(k.cylinder(lever[0], lever[1], 3, 17, 4, P, 20), { tone: "hi" }),
    L(k.knurl(lever[0], lever[1], 3, 17, 21, 16, P), { tone: "lo" }),
  ].join("") });
  return plate("RECORD") + painted(items);
}

// ---------- tier 2: the actors (four worker modules) ----------
const AGENTS = ["PLAN", "RSRCH", "WRITE", "CRIT"];
function actors() {
  const items = [];
  AGENTS.forEach((name, i) => {
    const plan = { x: -98 + i * 50, y: -50, w: 42, d: 78, r: 3 };
    const H = 22;
    const busy = i === 2;
    const out = [S(k.slabOf(plan, 0, H, P, 4, 0.9), { tone: busy ? "hi" : "mid", crease: "lo", lit: busy, inner: k.lineSvg(k.sideSeam(plan, 6, P, 4), { tone: "faint" }) })];
    out.push(L(k.planOutline(k.insetPlan(plan, 3.5), H, P, 3), { tone: "faint" }));
    for (let v = 0; v < 5; v++) {
      const y = plan.y + 10 + v * 5;
      out.push(L(k.onTop([[plan.x + 8, y], [plan.x + plan.w - 16, y], [plan.x + plan.w - 16, y + 2], [plan.x + 8, y + 2]], H, P, true), { tone: "lo" }));
    }
    const lamp = [plan.x + plan.w - 9, plan.y + 14];
    out.push(S(k.cylinder(lamp[0], lamp[1], 3.2, H, 1.2, P, 20), { tone: "mid" }));
    out.push(S(k.cylinder(lamp[0], lamp[1], 2.2, H + 1.2, 1.6, P, 20), { tone: busy ? "hi" : "lo", lit: busy }));
    const knob = [plan.x + plan.w - 10, plan.y + plan.d - 14];
    out.push(S(k.cylinder(knob[0], knob[1], 4.4, H, 3.6, P, 28, 0.4), { tone: "mid" }));
    out.push(L(k.knurl(knob[0], knob[1], 4.4, H, H + 3.6, 26, P), { tone: "lo" }));
    out.push(L(k.lineOnTop(knob, [knob[0] + 4, knob[1]], H + 3.6, P), { tone: "hi", free: "end" }));
    out.push(D([[plan.x + 4, plan.y + 4], [plan.x + 4, plan.y + plan.d - 4]].map(([x, y]) => at([x, y, H])), { size: 0.45 }));
    out.push(k.faceTextSvg(k.topMatrix([plan.x + 15, plan.y + plan.d - 9], H, P, "x"), name, { size: 3.4, tone: "mid", anchor: "middle" }));
    out.push(D(Array.from({ length: 6 }, (_, j) => at([plan.x + 7 + j * 5, plan.y + 4, H])), { size: 0.5, tone: "mid" }));
    items.push({ at: [plan.x + plan.w / 2, plan.y + plan.d / 2, 0], svg: out.join("") });
  });
  // the bus bar every module plugs into: modules never call each other, they share only this
  const bus = { x: -100, y: 34, w: 200, d: 8, r: 2 };
  items.push({ at: [0, 60, 0], svg: S(k.slabOf(bus, 0, 4, P, 3, 0.4), { tone: "lo" }) + D(Array.from({ length: 20 }, (_, j) => at([bus.x + 5 + j * 10, bus.y + 4, 4])), { size: 0.45 }) });
  return plate("ACTORS") + painted(items);
}

// ---------- tier 3: the queues (one channel per agent, id-only capsules, a 429 gauge) ----------
function queues() {
  const items = [];
  const CH = [-56, -30, -4, 22];
  CH.forEach((y, i) => {
    const out = [];
    for (const dy of [-6, 4]) out.push(S(k.slabOf({ x: -96, y: y + dy, w: 150, d: 2.4, r: 0.6 }, 0, 4, P, 2, 0.3), { tone: "mid" }));
    for (const x of [-100, 54]) out.push(S(k.slabOf({ x, y: y - 7, w: 4, d: 14, r: 1 }, 0, 7, P, 3, 0.4), { tone: "mid" }));
    // capsules waiting in this queue: each carries only a run id (the engraved line), never the work
    const caps = i === 1 ? [-70, -40, 6] : i === 2 ? [-50] : i === 0 ? [-20] : [];
    caps.forEach((cx, j) => {
      const lit = i === 1 && j === 2;
      const cap = { x: cx, y: y - 3.4, w: 22, d: 7, r: 3.4 };
      out.push(S(k.slabOf(cap, 0.6, 6, P, 6, 0.5), { tone: lit ? "hi" : "mid", crease: "lo", lit }));
      out.push(L(k.lineOnTop([cx + 7, y - 2], [cx + 7, y + 2], 6.6, P), { tone: lit ? "hi" : "lo" }));
    });
    out.push(D([at([-98, y, 7]), at([56, y, 7])], { size: 0.45 }));
    items.push({ at: [-20, y, 0], svg: out.join("") });
  });
  // the gauge: how long the agent's queue is paused after a 429 (needle at 30 s of 60)
  const g = [82, -30];
  const gOut = [S(k.cylinder(g[0], g[1], 19, 0, 8, P, 64, 0.8), { tone: "mid" })];
  gOut.push(L(k.knurl(g[0], g[1], 19, 5, 8, 72, P, 0.3), { tone: "lo" }));
  gOut.push(L(k.ring(g[0], g[1], 16.5, 8, P, 64), { tone: "lo" }));
  const ticks = k.radialTicks(g[0], g[1], 15.5, 60, 5, 8, [1.4, 3], P, -Math.PI * 0.75, Math.PI * 1.5);
  gOut.push(L(ticks.minor, { tone: "lo" }), L(ticks.major, { tone: "mid" }));
  const a = -Math.PI * 0.75 + Math.PI * 1.5 * 0.5;
  gOut.push(L(k.lineOnTop(g, [g[0] + Math.sin(a) * 13, g[1] - Math.cos(a) * 13], 8.2, P), { tone: "lit", free: "end" }));
  gOut.push(S(k.cylinder(g[0], g[1], 1.6, 8, 1.2, P, 16), { tone: "hi" }));
  gOut.push(k.faceTextSvg(k.topMatrix([g[0], g[1] + 9], 8, P, "x"), "429", { size: 3.2, tone: "lo", anchor: "middle" }));
  items.push({ at: [g[0], g[1], 0], svg: gOut.join("") });
  // the manifold where the channels end, with four ports
  const man = { x: 62, y: 4, w: 34, d: 48, r: 2 };
  const mOut = [S(k.slabOf(man, 0, 12, P, 3, 0.6), { tone: "mid" })];
  [0, 1, 2, 3].forEach((j) => mOut.push(L(k.ring(man.x + 9 + (j % 2) * 16, man.y + 12 + Math.floor(j / 2) * 22, 3.6, 12, P, 20), { tone: "lo" })));
  mOut.push(D([[man.x + 3, man.y + 3], [man.x + man.w - 3, man.y + man.d - 3]].map(([x, y]) => at([x, y, 12])), { size: 0.45 }));
  items.push({ at: [man.x + man.w / 2, man.y + man.d / 2, 0], svg: mOut.join("") });
  return plate("QUEUES") + painted(items);
}

// ---------- tier 4: the console (the request comes in here) ----------
function consoleTier() {
  const items = [];
  const body = { x: -92, y: -64, w: 128, d: 74, r: 3 };
  const bOut = [S(k.slabOf(body, 0, 12, P, 4, 0.8), { tone: "mid" })];
  const screen = k.insetPlan(body, 7);
  bOut.push(S(k.slabOf(screen, 12, 0.6, P, 3), { tone: "lo", crease: "none" }));
  bOut.push(L(k.planOutline(screen, 12.6, P, 3), { tone: "lo" }));
  [[0.25, 0.85], [0.42, 0.7], [0.59, 0.78], [0.76, 0.4]].forEach(([f, len], j) =>
    bOut.push(L(k.lineOnTop([screen.x + 8, screen.y + screen.d * f], [screen.x + 8 + (screen.w - 16) * len, screen.y + screen.d * f], 12.7, P), { tone: j === 0 ? "hi" : "mid", free: true })));
  bOut.push(D([[body.x + 3, body.y + 3], [body.x + body.w - 3, body.y + 3], [body.x + 3, body.y + body.d - 3], [body.x + body.w - 3, body.y + body.d - 3]].map(([x, y]) => at([x, y, 12])), { size: 0.45 }));
  items.push({ at: [body.x + body.w / 2, body.y + body.d / 2, 0], svg: bOut.join("") });
  const kb = { x: -92, y: 20, w: 128, d: 44, r: 3 };
  const kOut = [S(k.slabOf(kb, 0, 5, P, 4, 0.6), { tone: "mid" })];
  const keys = [];
  for (let r = 0; r < 3; r++) for (let c = 0; c < 12; c++) keys.push([kb.x + 5 + c * 10, kb.y + 5 + r * 12, c === 11 && r === 1]);
  keys.sort((p, q) => depth(p[0], p[1]) - depth(q[0], q[1]));
  for (const [x, y, submit] of keys) kOut.push(S(k.slabOf({ x, y, w: 8, d: 10, r: 1 }, 5, submit ? 3.4 : 2.6, P, 2, 0.3), { tone: submit ? "hi" : "mid", crease: "lo", lit: submit }));
  items.push({ at: [kb.x + kb.w / 2, kb.y + kb.d / 2, 0], svg: kOut.join("") });
  // the revision-cap dial (MAX_REVISIONS = 3)
  const d = [70, -30];
  const dOut = [S(k.cylinder(d[0], d[1], 14, 0, 9, P, 56, 0.6), { tone: "mid" })];
  dOut.push(L(k.knurl(d[0], d[1], 14, 0, 9, 60, P, 0.3), { tone: "lo" }));
  const dt = k.radialTicks(d[0], d[1], 11, 3, 1, 9, [2.2, 2.2], P, -Math.PI / 3, (Math.PI * 2) / 3);
  dOut.push(L(dt.major, { tone: "mid" }));
  dOut.push(L(k.lineOnTop(d, [d[0] + Math.sin(Math.PI / 3) * 9, d[1] - Math.cos(Math.PI / 3) * 9], 9.2, P), { tone: "hi", free: "end" }));
  items.push({ at: [d[0], d[1], 0], svg: dOut.join("") });
  const port = { x: 56, y: 18, w: 30, d: 40, r: 2 };
  items.push({ at: [port.x + 15, port.y + 20, 0], svg: S(k.slabOf(port, 0, 8, P, 3, 0.5), { tone: "mid" }) + L(k.ring(port.x + 15, port.y + 14, 5, 8, P, 24), { tone: "lo" }) + L(k.ring(port.x + 15, port.y + 14, 2.6, 8, P, 20), { tone: "mid" }) + D([at([port.x + 15, port.y + 31, 8])], { size: 0.5 }) });
  return plate("CONSOLE") + painted(items);
}

const tiers = { record: record(), actors: actors(), queues: queues(), console: consoleTier() };

// Where each tier's callouts point, in screen units with the tier at lift 0 (the page adds the tier's lift).
const anchors = {
  record: { a: at([-6, 34, 18]), b: at([67, -17, 8]) },
  actors: { a: at([-77, -30, 22]), b: at([33, -36, 25]) },
  queues: { a: at([17, -26, 6]), b: at([82, -30, 8]) },
  console: { a: at([-28, -27, 12]), b: at([70, -30, 9]) },
};
const lift1 = at([0, 0, 1])[1] - at([0, 0, 0])[1]; // screen y per world unit of lift (negative: up)

const out = { width: WIDTH, height: HEIGHT, gapShut: GAP_SHUT, gapOpen: GAP_OPEN, liftPerUnit: lift1, order: TIER_IDS, tiers, anchors };
mkdirSync(join(HERE, "../src/components/landing"), { recursive: true });
writeFileSync(join(HERE, "../src/components/landing/stack-art.json"), JSON.stringify(out));
console.log("wrote stack-art.json:", Object.values(tiers).reduce((n, s) => n + s.length, 0), "chars of SVG");

if (process.argv.includes("--preview")) {
  const body = TIER_IDS.map((id, i) => `<g transform="${k.translateAlong(P, [0, 0, i * GAP_OPEN])}">${tiers[id]}</g>`).join("");
  const svg = k.figureSvg({ width: WIDTH, height: HEIGHT, label: "preview", body: [body] });
  for (const theme of ["dark", "light"]) {
    writeFileSync(join(HERE, `../.stack-preview-${theme}.html`), k.pageHtml({ title: "stack", theme, body: k.plateHtml({ fig: "Fig 1", title: "The scheduler, exploded", hint: "", readout: "", body: svg }), width: 620 }));
  }
  console.log("wrote .stack-preview-{dark,light}.html");
}
