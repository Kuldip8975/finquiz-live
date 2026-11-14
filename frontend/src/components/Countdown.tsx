import { useEffect, useState } from "react";

interface Props {
  startedAt?: number;
  endsAt: number;
  offset: number; // server clock minus this device's clock
  variant: "ring" | "bar";
}

/**
 * Time left on the current question, as a ring (projector) or a bar (phone).
 * Times are server times; `offset` corrects for a phone with a wrong clock.
 * The server alone decides when the question closes: this is only a display.
 */
export function Countdown({ startedAt, endsAt, offset, variant }: Props) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 100);
    return () => clearInterval(id);
  }, []);

  const serverNow = now + offset;
  const total = startedAt ? endsAt - startedAt : 20000;
  const leftMs = Math.max(0, endsAt - serverNow);
  const seconds = Math.ceil(leftMs / 1000);
  const fraction = Math.min(1, leftMs / total);
  const urgent = seconds <= 5;
  const label = `${seconds} seconds left`;

  if (variant === "bar") {
    return (
      <div className={`timer-bar ${urgent ? "urgent" : ""}`} role="timer" aria-label={label}>
        <div className="timer-bar-track">
          <div className="timer-bar-fill" style={{ transform: `scaleX(${fraction})` }} />
        </div>
        <span className="timer-bar-num">{seconds}</span>
      </div>
    );
  }

  const r = 54;
  const circumference = 2 * Math.PI * r;
  return (
    <div className={`timer-ring ${urgent ? "urgent" : ""}`} role="timer" aria-label={label}>
      <svg viewBox="0 0 120 120" aria-hidden>
        <circle className="timer-ring-track" cx="60" cy="60" r={r} />
        <circle
          className="timer-ring-fill"
          cx="60"
          cy="60"
          r={r}
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - fraction)}
        />
      </svg>
      <span>{seconds}</span>
    </div>
  );
}
