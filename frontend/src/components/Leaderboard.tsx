import type { Ranked } from "../types";
import { Avatar } from "./Flair";

interface Props {
  rows: Ranked[];
  limit?: number;
  /** name -> places moved since the last question (+2 = up two places). */
  moves?: Record<string, number>;
}

/** Ranked list of players. Top three get a coloured medal. */
export function Leaderboard({ rows, limit, moves = {} }: Props) {
  const shown = limit ? rows.slice(0, limit) : rows;
  return (
    <ol className="leaderboard">
      {shown.map((r, i) => {
        const move = moves[r.name] ?? 0;
        return (
          <li key={r.name} className={r.rank <= 3 ? `top top-${r.rank}` : ""} style={{ animationDelay: `${i * 50}ms` }}>
            <span className="rank">{r.rank}</span>
            <span className="who">
              <Avatar name={r.name} size={34} />
              <span className="name">{r.name}</span>
              {move !== 0 && (
                <span
                  className={`move ${move > 0 ? "up" : "down"}`}
                  aria-label={`${move > 0 ? "up" : "down"} ${Math.abs(move)}`}
                >
                  {move > 0 ? "▲" : "▼"}
                  {Math.abs(move)}
                </span>
              )}
            </span>
            <span className="score">{r.score.toLocaleString()}</span>
          </li>
        );
      })}
      {limit && rows.length > limit && <li className="more">+ {rows.length - limit} more</li>}
    </ol>
  );
}

/** First, second and third place on steps, for the final screen. */
export function Podium({ rows }: { rows: Ranked[] }) {
  const top = rows.slice(0, 3);
  // Show second on the left, first in the middle, third on the right.
  const order = [top[1], top[0], top[2]].filter(Boolean) as Ranked[];
  return (
    <div className="podium" aria-label="Top three">
      {order.map((r) => (
        <div key={r.name} className={`step step-${r.rank}`}>
          {r.rank === 1 && (
            <span className="crown" aria-hidden>
              👑
            </span>
          )}
          <Avatar name={r.name} size={r.rank === 1 ? 72 : 56} />
          <div className="step-name">{r.name}</div>
          <div className="step-score">{r.score.toLocaleString()} pts</div>
          <div className="step-block">
            <span>{r.rank}</span>
          </div>
        </div>
      ))}
    </div>
  );
}
