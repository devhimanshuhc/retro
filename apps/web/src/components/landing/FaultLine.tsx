import art from "./faultline-art.json";
import { FaultStage } from "./FaultStage";

const STEPS = [
  { title: "A worker crashes mid-step", body: "The Writer's process dies halfway through a draft. In a typical agent chain, the whole run dies with it." },
  { title: "Its messages wait", body: "Here nothing is lost: each message sits in the Writer's queue, holding only the run's id. The other agents keep working." },
  { title: "A fresh worker takes over", body: "Another Writer picks the job up and reads the run from its record, starting the step cleanly." },
  { title: "The work flows on, once", body: "The step finishes exactly once, with no duplicate drafts, and the next agent gets its message as if nothing happened." },
];

/** A line of agent stations (Anatomy kit) where one crashes and recovers as the visitor scrolls. */
export function FaultLine() {
  const svg = (
    <svg viewBox={`0 0 ${art.width} ${art.height}`} className="iso-svg" role="img"
      aria-label="Four agent stations on a rail, joined by queue trays. The third station has crashed and floats above its place with a red lamp while three messages wait in the tray before it; a fresh station drops in and the messages move on.">
      <g dangerouslySetInnerHTML={{ __html: art.base + art.stationsBefore }} />
      {art.capsules.map((c, i) => <g key={i} data-capsule={i} dangerouslySetInnerHTML={{ __html: c }} />)}
      <g data-crashed dangerouslySetInnerHTML={{ __html: art.crashed }} />
      <g dangerouslySetInnerHTML={{ __html: art.stationsAfter }} />
    </svg>
  );
  return <FaultStage steps={STEPS} figure={svg} geometry={{ lift: art.lift, travel: art.travel, xUnit: art.xUnit, zUnit: art.zUnit }} />;
}
