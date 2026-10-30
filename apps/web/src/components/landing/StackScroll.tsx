import art from "./stack-art.json";
import { StackStage, type Step } from "./StackStage";

// Top tier first, as the page reads them. `tier` is the figure's tier id (scripts/build-stack.mjs).
const STEPS: Step[] = [
  {
    tier: "console", label: "Your request", title: "Ask once",
    body: "You write one request. The API saves it, puts a message on the planner's queue and answers in about 20 ms. The work happens elsewhere.",
    callouts: ["Prompt in", "Revision cap: 3"],
  },
  {
    tier: "queues", label: "The queues", title: "Hand off",
    body: "Agents never call each other. Each passes a short message holding one run id through its own queue. A rate limit pauses only that agent's queue until it resets.",
    callouts: ["Ids only, never the work", "429 pause"],
  },
  {
    tier: "actors", label: "The actors", title: "Work alone",
    body: "Planner, Researcher, Writer and Critic run as separate processes. Kill one mid-step and another takes the job back when its lock expires, with no duplicate output.",
    callouts: ["One process per agent", "Busy: writing draft 2"],
  },
  {
    tier: "record", label: "The record", title: "Remember everything",
    body: "Every output, step and event is kept in one record of the run. A job that fails three times lands in the dead-letter queue with its error, ready to replay.",
    callouts: ["This run's document", "Dead letters"],
  },
];

/** The scheduler as an exploded isometric rack (built with the Anatomy kit). Server-rendered art; the client
 * stage only moves the tiers and the callouts as the visitor scrolls. */
export function StackScroll() {
  const svg = (
    <svg viewBox={`0 0 ${art.width} ${art.height}`} className="iso-svg" role="img"
      aria-label="An exploded rack. Top: a console where the request is typed. Then a queue manifold whose channels carry id-only capsules and a gauge for rate-limit pauses. Then the worker modules, one per agent, the writer's lamp lit. Bottom: a cabinet of run documents with one drawer pulled out, and a red dead-letter tray with a replay lever.">
      {art.order.map((id) => (
        <g key={id} data-tier={id} dangerouslySetInnerHTML={{ __html: (art.tiers as Record<string, string>)[id] }} />
      ))}
      <g data-callouts />
    </svg>
  );
  return (
    <StackStage steps={STEPS} figure={svg} geometry={{ width: art.width, height: art.height, gapShut: art.gapShut, gapOpen: art.gapOpen, liftPerUnit: art.liftPerUnit, order: art.order, anchors: art.anchors as Record<string, { a: number[]; b: number[] }> }} />
  );
}
