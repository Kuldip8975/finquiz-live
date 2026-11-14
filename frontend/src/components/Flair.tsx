// Small visual pieces. They only change how things look; no game logic here.
import { useEffect, useState } from "react";

const AVATAR_COLOURS = ["#0f766e", "#3e63dd", "#d97706", "#c2332f", "#7c3aed", "#15803d", "#db2777", "#0369a1"];

/** A coloured circle with a player's initials. Same name -> same colour. */
export function Avatar({ name, size = 36 }: { name: string; size?: number }) {
  let hash = 0;
  for (const ch of name) hash = (hash * 31 + ch.codePointAt(0)!) >>> 0;
  const initials = name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => [...w][0]!.toUpperCase())
    .join("");
  return (
    <span
      className="avatar"
      aria-hidden
      style={{ background: AVATAR_COLOURS[hash % AVATAR_COLOURS.length], width: size, height: size, fontSize: size * 0.4 }}
    >
      {initials}
    </span>
  );
}

/** ●●●○○ : which question we are on. */
export function ProgressDots({ current, total }: { current: number; total: number }) {
  return (
    <span className="dots" role="img" aria-label={`Question ${current + 1} of ${total}`}>
      {Array.from({ length: total }, (_, i) => (
        <span key={i} className={i < current ? "done" : i === current ? "now" : ""} />
      ))}
      <b>
        {current + 1}/{total}
      </b>
    </span>
  );
}

/** Counts up from 0 to `value` in about 0.8 s. */
export function CountUp({ value }: { value: number }) {
  const [shown, setShown] = useState(0);
  useEffect(() => {
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) {
      setShown(value);
      return;
    }
    let frame = 0;
    const start = performance.now();
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / 800);
      setShown(Math.round(value * (1 - Math.pow(1 - t, 3))));
      if (t < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [value]);
  return <>{shown.toLocaleString()}</>;
}

const CONFETTI_COLOURS = ["#f5b301", "#0f766e", "#e5484d", "#3e63dd", "#15803d", "#db2777"];

/** A short burst of falling confetti (pure CSS animation). */
export function Confetti({ pieces = 70 }: { pieces?: number }) {
  // Positions are chosen once per mount so the pieces do not jump on re-render.
  const [bits] = useState(() =>
    Array.from({ length: pieces }, (_, i) => ({
      left: Math.random() * 100,
      delay: Math.random() * 1.2,
      duration: 2.4 + Math.random() * 1.8,
      size: 6 + Math.random() * 8,
      colour: CONFETTI_COLOURS[i % CONFETTI_COLOURS.length],
      round: Math.random() > 0.6,
    })),
  );
  return (
    <div className="confetti" aria-hidden>
      {bits.map((b, i) => (
        <span
          key={i}
          style={{
            left: `${b.left}%`,
            width: b.size,
            height: b.round ? b.size : b.size * 0.45,
            background: b.colour,
            borderRadius: b.round ? "50%" : "2px",
            animationDelay: `${b.delay}s`,
            animationDuration: `${b.duration}s`,
          }}
        />
      ))}
    </div>
  );
}
