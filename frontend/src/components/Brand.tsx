import type { ReactNode } from "react";

/** App name with a small coin mark, shown at the top of every screen. */
export function Brand({ right }: { right?: ReactNode }) {
  return (
    <header className="brand-bar">
      <div className="brand">
        <span className="brand-mark" aria-hidden>₹</span>
        <span className="brand-name">FinQuiz Live</span>
      </div>
      {right && <div className="brand-right">{right}</div>}
    </header>
  );
}
