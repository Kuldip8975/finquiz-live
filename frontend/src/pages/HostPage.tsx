import { useCallback, useEffect, useRef, useState } from "react";
import QRCode from "qrcode";
import { call, CallError, socket } from "../socket";
import { clear, load, save } from "../storage";
import type { HostView } from "../types";
import { useConnection } from "../useConnection";
import { useWakeLock } from "../useWakeLock";
import { Countdown } from "../components/Countdown";
import { ErrorPanel } from "../components/ErrorPanel";
import { Avatar, Confetti, ProgressDots } from "../components/Flair";
import { Brand } from "../components/Brand";
import { Leaderboard, Podium } from "../components/Leaderboard";
import { StatusBanner } from "../components/StatusBanner";
import { LETTERS } from "../components/letters";

const KEY = "quiz.host";
interface Saved {
  code: string;
  hostToken: string;
}

export function HostPage() {
  const [view, setView] = useState<HostView | null>(null);
  const [offset, setOffset] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<{ message: string; retry?: () => void } | null>(null);

  const apply = useCallback((v: HostView) => {
    setView(v);
    setOffset(v.serverNow - Date.now());
  }, []);

  // On every (re)connection: take back the room this screen already hosts,
  // or create a new one. The host token never appears in the URL.
  const open = useCallback(async () => {
    setError(null);
    try {
      const saved = load<Saved>(KEY);
      if (saved) {
        try {
          const r = await call<{ state: HostView }>("host:resume", { ...saved });
          apply(r.state);
          return;
        } catch (e) {
          const code = (e as CallError).code;
          if (code !== "room_not_found" && code !== "not_host") throw e;
          clear(KEY);
        }
      }
      const r = await call<{ code: string; hostToken: string; state: HostView }>("host:create");
      save(KEY, { code: r.code, hostToken: r.hostToken });
      apply(r.state);
    } catch (e) {
      setError({ message: (e as CallError).message, retry: () => void open() });
    }
  }, [apply]);

  const { status, retry } = useConnection(open);
  useWakeLock(view !== null && view.phase !== "finished");

  useEffect(() => {
    const onState = (v: HostView) => v.role === "host" && apply(v);
    socket.on("state", onState);
    return () => {
      socket.off("state", onState);
    };
  }, [apply]);

  async function next() {
    setBusy(true);
    setError(null);
    try {
      await call("host:next");
    } catch (e) {
      const err = e as CallError;
      if (err.code === "not_joined") void open();
      setError({ message: err.message, retry: () => void next() });
    } finally {
      setBusy(false);
    }
  }

  function newGame() {
    clear(KEY);
    setView(null);
    void open();
  }

  // Rank movement since the previous question, worked out on this screen
  // from the leaderboards it has already been sent (display only).
  const ranksSeen = useRef({ index: -1, ranks: new Map<string, number>(), moves: {} as Record<string, number> });
  if (view?.phase === "reveal" && view.leaderboard && ranksSeen.current.index !== view.questionIndex) {
    const moves: Record<string, number> = {};
    for (const r of view.leaderboard) {
      const before = ranksSeen.current.ranks.get(r.name);
      if (before) moves[r.name] = before - r.rank;
    }
    ranksSeen.current = {
      index: view.questionIndex,
      ranks: new Map(view.leaderboard.map((r) => [r.name, r.rank])),
      moves,
    };
  }

  let body;
  if (!view) {
    body = !error && <p className="loading">Opening a room…</p>;
  } else if (view.phase === "lobby") {
    body = <Lobby view={view} busy={busy} onStart={next} />;
  } else if (view.phase === "question" && view.question) {
    body = (
      <section className="host-question fade-in" key={`q${view.questionIndex}`}>
        <div className="host-q-top">
          {view.endsAt && (
            <Countdown variant="ring" startedAt={view.startedAt} endsAt={view.endsAt} offset={offset} />
          )}
          <div className="answered" aria-live="polite">
            <span className="answered-num">{view.answeredCount}</span>
            <span>of {view.playerCount} answered</span>
            <span className="answered-track" aria-hidden>
              <span
                style={{ transform: `scaleX(${view.playerCount ? (view.answeredCount ?? 0) / view.playerCount : 0})` }}
              />
            </span>
          </div>
        </div>
        <h1 className="q-text">{view.question.text}</h1>
        <div className="options host-options">
          {view.question.options.map((opt, i) => (
            <div key={i} className={`option opt-${i}`}>
              <span className="letter">{LETTERS[i]}</span>
              <span>{opt}</span>
            </div>
          ))}
        </div>
      </section>
    );
  } else if (view.phase === "reveal" && view.question) {
    const q = view.question;
    const counts = view.answerCounts ?? [0, 0, 0, 0];
    const most = Math.max(1, ...counts);
    body = (
      <div className="reveal-grid fade-in" key={`r${view.questionIndex}`}>
        <section className="panel">
          <h2 className="reveal-q">{q.text}</h2>
          <div className="answer-bars">
            {q.options.map((opt, i) => (
              <div key={i} className={`answer-bar ${i === q.correctIndex ? "correct" : ""}`}>
                <div className={`answer-bar-fill fill-${i}`} style={{ transform: `scaleX(${counts[i] / most})` }} />
                <span className={`letter letter-${i}`}>{i === q.correctIndex ? "✓" : LETTERS[i]}</span>
                <span className="answer-text">{opt}</span>
                <span className="count">{counts[i]}</span>
              </div>
            ))}
          </div>
          {q.explanation && (
            <div className="explain">
              <p>{q.explanation}</p>
              {q.source?.startsWith("https://") && (
                <a href={q.source} target="_blank" rel="noreferrer">
                  Source: {new URL(q.source).hostname}
                </a>
              )}
            </div>
          )}
        </section>
        <section className="panel">
          <h2>Leaderboard</h2>
          <Leaderboard rows={view.leaderboard ?? []} limit={8} moves={ranksSeen.current.moves} />
          <button className="btn big-btn" disabled={busy} onClick={next}>
            {view.isLastQuestion ? "Show final ranking" : "Next question →"}
          </button>
        </section>
      </div>
    );
  } else if (view.phase === "finished") {
    const rows = view.leaderboard ?? [];
    body = (
      <section className="final fade-in">
        <Confetti />
        <p className="eyebrow center-text">Quiz complete</p>
        <h1>Final ranking</h1>
        <Podium rows={rows} />
        {rows.length > 3 && <Leaderboard rows={rows.slice(3)} />}
        <button className="btn secondary" onClick={newGame}>
          Start a new game
        </button>
      </section>
    );
  }

  const progress =
    view && (view.phase === "question" || view.phase === "reveal") ? (
      <ProgressDots current={view.questionIndex} total={view.totalQuestions} />
    ) : view ? (
      <span className="pill">Room {view.code}</span>
    ) : null;

  return (
    <main className="page host">
      <Brand right={progress} />
      <StatusBanner status={status} retry={retry} />
      {error && <ErrorPanel message={error.message} onRetry={error.retry} />}
      {body}
    </main>
  );
}

function Lobby({ view, busy, onStart }: { view: HostView; busy: boolean; onStart: () => void }) {
  const joinUrl = `${location.origin}/?code=${view.code}`;
  const [qr, setQr] = useState("");

  useEffect(() => {
    QRCode.toDataURL(joinUrl, { margin: 1, width: 360 }).then(setQr).catch(() => setQr(""));
  }, [joinUrl]);

  const players = view.players ?? [];
  return (
    <section className="lobby fade-in">
      <div className="join-card">
        <ol className="join-steps">
          <li>
            Open <strong>{location.host}</strong> on your phone
          </li>
          <li>Enter this room code</li>
        </ol>
        <div className="room-code" aria-label={`Room code ${view.code.split("").join(" ")}`}>
          {view.code}
        </div>
        {qr && (
          <div className="qr-wrap">
            <img className="qr" src={qr} alt={`QR code to join room ${view.code}`} />
            <span>or scan to join</span>
          </div>
        )}
      </div>
      <div className="panel lobby-players">
        <div className="lobby-head">
          <h2>Players</h2>
          <span className="count-badge" aria-live="polite">
            {view.playerCount}
          </span>
        </div>
        {players.length === 0 ? (
          <p className="empty">Waiting for players to join…</p>
        ) : (
          <ul className="chips">
            {players.map((n) => (
              <li key={n}>
                <Avatar name={n} size={34} />
                {n}
              </li>
            ))}
          </ul>
        )}
        <button className="btn big-btn" disabled={busy || view.playerCount === 0} onClick={onStart}>
          {view.playerCount === 0
            ? "Waiting for players…"
            : `Start quiz with ${view.playerCount} player${view.playerCount === 1 ? "" : "s"}`}
        </button>
      </div>
    </section>
  );
}
