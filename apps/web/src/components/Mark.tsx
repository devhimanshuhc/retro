import { useId } from "react";

/** Retro's glyph: four agents as four cells; the lit one (with CRT scanlines) is working now, and the dots between
 * the cells are messages going round the loop. Original art. */
export function Mark({ className = "" }: { className?: string }) {
  const id = useId();
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden fill="none">
      <mask id={id}>
        <rect width="32" height="32" fill="#fff" />
        <rect x="17" y="22.6" width="13" height="1.1" fill="#000" />
        <rect x="17" y="25.3" width="13" height="1.1" fill="#000" />
      </mask>
      <rect x="4.5" y="4.5" width="9" height="9" rx="2.6" stroke="currentColor" strokeWidth="1.9" />
      <rect x="18.5" y="4.5" width="9" height="9" rx="2.6" stroke="currentColor" strokeWidth="1.9" />
      <rect x="4.5" y="18.5" width="9" height="9" rx="2.6" stroke="currentColor" strokeWidth="1.9" />
      <rect x="17.55" y="17.55" width="10.9" height="10.9" rx="3.5" fill="currentColor" mask={`url(#${id})`} />
      <circle cx="16" cy="9" r="1.25" fill="currentColor" />
      <circle cx="23" cy="16" r="1.25" fill="currentColor" />
      <circle cx="16" cy="23" r="1.25" fill="currentColor" opacity=".45" />
      <circle cx="9" cy="16" r="1.25" fill="currentColor" opacity=".45" />
    </svg>
  );
}

/** The name with its glyph, as every page shows it. */
export function Wordmark({ size = "md" }: { size?: "md" | "lg" }) {
  return (
    <span className={`flex items-center gap-2.5 font-serif leading-none tracking-tight ${size === "lg" ? "text-[1.6rem]" : "text-[1.4rem]"}`}>
      <Mark className={size === "lg" ? "size-7" : "size-6"} />
      Retro
    </span>
  );
}
