// The shapes of what the server sends. These mirror host_view / player_view
// in backend/game.py.

export type Phase = "lobby" | "question" | "reveal" | "finished";

export interface Question {
  index: number;
  text: string;
  options: string[];
  // Only present after the question has closed:
  correctIndex?: number;
  explanation?: string;
  source?: string;
}

export interface Ranked {
  name: string;
  score: number;
  rank: number;
}

interface BaseView {
  code: string;
  phase: Phase;
  questionIndex: number;
  totalQuestions: number;
  playerCount: number;
  serverNow: number; // server clock in ms, used to keep countdowns in sync
}

export interface HostView extends BaseView {
  role: "host";
  players?: string[];
  question?: Question;
  startedAt?: number;
  endsAt?: number;
  answeredCount?: number;
  answerCounts?: number[];
  leaderboard?: Ranked[];
  isLastQuestion?: boolean;
}

export interface PlayerView extends BaseView {
  role: "player";
  name: string;
  question?: Question;
  startedAt?: number;
  endsAt?: number;
  myChoice?: number | null;
  wasCorrect?: boolean;
  pointsGained?: number;
  score?: number;
  rank?: number;
  // Is the teacher's screen connected? If not, since when (server time, ms).
  hostOnline?: boolean;
  hostAwaySince?: number;
}
