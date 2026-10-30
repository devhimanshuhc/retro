import { Composer } from "@/components/Composer";
import { KeyGate } from "@/components/KeyGate";

const SUGGESTIONS = [
  "Nvidia's latest quarterly earnings",
  "State of solid-state batteries",
  "GLP-1 drugs and heart disease",
];

export default function NewRun() {
  return (
    <div className="mx-auto flex min-h-full max-w-2xl flex-col justify-center gap-6 px-5 py-16">
      <div className="flex flex-col gap-2 text-center">
        <h1 className="font-serif text-[clamp(1.8rem,3.4vw,2.4rem)] leading-tight tracking-[-0.015em]">
          What should the agents research?
        </h1>
        <p className="text-sm text-muted">They plan, read real sources, write a cited report and review it.</p>
      </div>
      <KeyGate>
        <Composer suggestions={SUGGESTIONS} autoFocus />
      </KeyGate>
    </div>
  );
}
