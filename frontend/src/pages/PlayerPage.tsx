import { type FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { call, CallError, socket } from "../socket";
import { clear, load, save } from "../storage";
import type { PlayerView } from "../types";
import { useConnection } from "../useConnection";
import { useWakeLock } from "../useWakeLock";
import { Countdown } from "../components/Countdown";
import { Brand } from "../components/Brand";
import { ErrorPanel } from "../components/ErrorPanel";
import { Avatar, Confetti, CountUp, ProgressDots } from "../components/Flair";
import { StatusBanner } from "../components/StatusBanner";
import { LETTERS } from "../components/letters";

const KEY = "quiz.player";
const HOST_GRACE_MS = 5000; // ignore a quick host refresh
const HOST_LEFT_MS = 10 * 60 * 1000; // after this, tell the player the quiz has stopped
interface Saved {
  code: string;
  token: string;
}

export function PlayerPage() {
  const [view, setView] = useState<PlayerView | null>(null);
  const [offset, setOffset] = useState(0);
  const [resuming, setResuming] = useState(() => load<Saved>(KEY) !== null);
  const [error, setError] = useState<{ message: string; retry?: () => void } | null>(null);
  const [pendingChoice, setPendingChoice] = useState<number | null>(null);

  const apply = useCallback((v: PlayerView) => {
    setView(v);
    setOffset(v.serverNow - Date.now());
  }, []);

  // Runs on every (re)connection. If this phone has joined before, rejoin
  // the same game with the saved token: this is what makes refresh safe.
  const resume = useCallback(async () => {
    const saved = load<Saved>(KEY);
    if (!saved) return;
    setResuming(true);
    setError(null);
    try {
      const r = await call<{ state: PlayerView }>("player:resume", { ...saved });
      apply(r.state);
    } catch (e) {
      const err = e as CallError;
      if (err.code === "player_not_found" || err.code === "room_not_found") {
        clear(KEY);
        setView(null);
        setError({ message: "That game is no longer running. Join a new one with the code on the projector." });
      } else {
        setError({ message: err.message, retry: () => void resume() });
      }
    } finally {
      setResuming(false);
    }
  }, [apply]);

  const { status, retry } = useConnection(resume);
  useWakeLock(view !== null && view.phase !== "finished");

  useEffect(() => {
    const onState = (v: PlayerView) => v.role === "player" && apply(v);
    socket.on("state", onState);
    return () => {
      socket.off("state", onState);
    };
  }, [apply]);

  // Once an answer is locked in, make sure the confirmation is on screen
  // (on a short phone it can sit below the four buttons).
  const lockedRef = useRef<HTMLParagraphElement>(null);
  useEffect(() => {
    if (view?.phase === "question" && view.myChoice != null) {
      lockedRef.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  }, [view?.phase, view?.myChoice]);

  // A new question clears the tapped option.
  useEffect(() => setPendingChoice(null), [view?.questionIndex, view?.phase]);

  async function answer(choice: number) {
    if (!view?.question || view.myChoice != null || pendingChoice != null) return;
    setPendingChoice(choice);
    setError(null);
    navigator.vibrate?.(20); // a small tap feel on phones that support it
    try {
      const r = await call<{ state: PlayerView }>("player:answer", {
        questionIndex: view.questionIndex,
        choice,
      });
      apply(r.state);
    } catch (e) {
      const err = e as CallError;
      if (err.code === "already_answered" || err.code === "closed") return; // a fresh state is on its way
      setPendingChoice(null);
      if (err.code === "not_joined") void resume();
      setError({ message: `${err.message} Tap your answer again.` });
    }
  }

  function leave() {
    clear(KEY);
    setView(null);
  }

  // The teacher's screen may close (tab shut, laptop asleep). The game waits
  // for it, but the phone must say so instead of looking frozen (rule 4).
  const [clock, setClock] = useState(() => Date.now());
  const hostMissing = view !== null && view.hostOnline === false && view.phase !== "finished";
  useEffect(() => {
    if (!hostMissing) return;
    const id = setInterval(() => setClock(Date.now()), 1000);
    return () => clearInterval(id);
  }, [hostMissing]);
  const awayMs = hostMissing && view?.hostAwaySince ? clock + offset - view.hostAwaySince : 0;
  const hostLeft = hostMissing && awayMs > HOST_LEFT_MS;
  const hostAway = hostMissing && awayMs > HOST_GRACE_MS && !hostLeft;

  let body;
  if (!view && resuming) {
    body = <p className="loading">Rejoining your game…</p>;
  } else if (!view) {
    body = (
      <JoinForm
        online={status === "online"}
        onJoined={(token, v) => {
          save(KEY, { code: v.code, token });
          apply(v);
        }}
      />
    );
  } else if (view.phase === "lobby") {
    body = (
      <div className="card center-text fade-in">
        <div className="lobby-avatar pop">
          <Avatar name={view.name} size={84} />
          <span className="lobby-tick" aria-hidden>
            ✓
          </span>
        </div>
        <h1>You're in, {view.name}!</h1>
        <p>Look at the projector. The quiz will start soon.</p>
        <div className="waiting" aria-hidden>
          <span />
          <span />
          <span />
        </div>
        <p className="muted small">
          {view.playerCount} player{view.playerCount === 1 ? "" : "s"} in room <strong>{view.code}</strong>
        </p>
        <button className="link" onClick={leave}>
          Not you? Leave
        </button>
      </div>
    );
  } else if (view.phase === "question" && view.question) {
    const chosen = view.myChoice ?? pendingChoice;
    body = (
      <section className="fade-in" key={`q${view.questionIndex}`}>
        {view.endsAt && <Countdown variant="bar" startedAt={view.startedAt} endsAt={view.endsAt} offset={offset} />}
        <h2 className="q-text">{view.question.text}</h2>
        <div className="options">
          {view.question.options.map((opt, i) => (
            <button
              key={i}
              className={`option opt-${i} ${chosen === i ? "chosen" : ""} ${chosen != null && chosen !== i ? "dim" : ""}`}
              disabled={chosen != null}
              aria-pressed={chosen === i}
              onClick={() => answer(i)}
            >
              <span className="letter">{LETTERS[i]}</span>
              <span>{opt}</span>
            </button>
          ))}
        </div>
        {view.myChoice != null && (
          <p className="locked" role="status" ref={lockedRef}>
            ✓ Answer locked in. Watch the projector.
          </p>
        )}
        {pendingChoice != null && view.myChoice == null && <p className="loading small">Sending…</p>}
      </section>
    );
  } else if (view.phase === "reveal" && view.question) {
    const q = view.question;
    const answered = view.myChoice != null;
    const tone = view.wasCorrect ? "good" : answered ? "bad" : "none";
    body = (
      <div className={`card center-text result fade-in ${tone}`} key={`r${view.questionIndex}`} role="status">
        <div className={`result-icon ${tone} pop`} aria-hidden>
          {view.wasCorrect ? "✓" : answered ? "✗" : "–"}
        </div>
        <h1>{view.wasCorrect ? "Correct!" : answered ? "Not quite" : "Time's up"}</h1>
        {view.wasCorrect && (
          <p className="points">
            +<CountUp value={view.pointsGained ?? 0} /> points
          </p>
        )}
        <div className="correct-answer">
          <span className="muted small">Correct answer</span>
          <strong>
            {LETTERS[q.correctIndex!]}. {q.options[q.correctIndex!]}
          </strong>
        </div>
        {q.explanation && <p className="muted">{q.explanation}</p>}
        <div className="stats">
          <div>
            <span className="big">
              <CountUp value={view.score ?? 0} />
            </span>
            total points
          </div>
          <div>
            <span className="big">#{view.rank}</span>of {view.playerCount}
          </div>
        </div>
        <p className="muted small">
          {view.questionIndex + 1 >= view.totalQuestions ? "Final results coming up…" : "Next question coming up…"}
        </p>
      </div>
    );
  } else if (view.phase === "finished") {
    body = (
      <div className="card center-text fade-in">
        {view.rank != null && view.rank <= 3 && <Confetti pieces={45} />}
        <p className="eyebrow">Final result</p>
        <div className={`final-rank pop ${view.rank && view.rank <= 3 ? `medal-${view.rank}` : ""}`}>#{view.rank}</div>
        <p>
          out of {view.playerCount} players · <strong>{view.score?.toLocaleString()}</strong> points
        </p>
        <p className="muted">Thanks for playing, {view.name}!</p>
        <button className="btn secondary" onClick={leave}>
          Join another game
        </button>
      </div>
    );
  }

  if (view && hostLeft) {
    body = (
      <div className="card center-text fade-in" role="status">
        <div className="result-icon none" aria-hidden>
          ⏸
        </div>
        <h1>The teacher has left this quiz</h1>
        <p className="muted">
          The host screen has been closed for a while, so the quiz can't continue right now.
          {view.score != null && (
            <>
              {" "}
              You finished with <strong>{view.score.toLocaleString()}</strong> points.
            </>
          )}
        </p>
        <p className="muted small">If the teacher reopens it, this screen will carry on by itself.</p>
        <button className="btn secondary" onClick={leave}>
          Join another game
        </button>
      </div>
    );
  }

  const progress =
    view && (view.phase === "question" || view.phase === "reveal") ? (
      <ProgressDots current={view.questionIndex} total={view.totalQuestions} />
    ) : view ? (
      <span className="pill pill-user">
        <Avatar name={view.name} size={22} />
        {view.name}
      </span>
    ) : null;

  // The whole phone screen takes the colour of the result.
  const tone =
    view?.phase === "reveal" ? (view.wasCorrect ? "tone-good" : view.myChoice != null ? "tone-bad" : "tone-none") : "";

  return (
    <main className={`page player ${tone}`}>
      <Brand right={progress} />
      <StatusBanner status={status} retry={retry} />
      {error && <ErrorPanel message={error.message} onRetry={error.retry} />}
      {hostAway && (
        <div className="banner" role="status">
          <span className="spinner" aria-hidden />
          <span>The teacher's screen disconnected. Waiting for it to come back…</span>
        </div>
      )}
      {body}
    </main>
  );
}

function JoinForm({ online, onJoined }: { online: boolean; onJoined: (token: string, v: PlayerView) => void }) {
  const [code, setCode] = useState(() => (new URLSearchParams(location.search).get("code") ?? "").toUpperCase());
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMessage("");
    try {
      const r = await call<{ token: string; state: PlayerView }>("player:join", {
        code: code.trim(),
        name: name.trim(),
      });
      onJoined(r.token, r.state);
    } catch (err) {
      setMessage((err as CallError).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="hero fade-in" aria-hidden>
        <div className="coins">
          <span className="coin c1">₹</span>
          <span className="coin c2">₹</span>
          <span className="coin c3">₹</span>
        </div>
        <p className="hero-line">Quick money questions, against the clock</p>
      </div>
    <form className="card join fade-in" onSubmit={submit}>
      <h1>Join the quiz</h1>
      <p className="muted">Enter the code shown on the projector.</p>
      <label>
        Room code
        <input
          className="code-input"
          value={code}
          onChange={(e) => setCode(e.target.value.toUpperCase().replace(/[^A-Z]/g, ""))}
          maxLength={5}
          autoCapitalize="characters"
          autoComplete="off"
          autoCorrect="off"
          spellCheck={false}
          placeholder="ABCDE"
          aria-invalid={!!message}
          required
        />
      </label>
      <label>
        Your name
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          maxLength={20}
          autoComplete="nickname"
          placeholder="e.g. Asha"
          required
        />
      </label>
      {message && (
        <p className="form-error" role="alert">
          {message}
        </p>
      )}
      <button className="btn" disabled={busy || !online}>
        {busy ? "Joining…" : online ? "Join" : "Connecting…"}
      </button>
    </form>
    </>
  );
}
