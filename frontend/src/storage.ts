// Small wrapper around localStorage for the saved host/player token.
//
// - Some browsers (private mode, strict settings) throw when localStorage is
//   touched, so every access is guarded and we fall back to memory for this tab.
// - Saved sessions expire after MAX_AGE, so on a shared school computer the
//   next person does not walk into the previous person's game.

const MAX_AGE_MS = 4 * 60 * 60 * 1000; // 4 hours: longer than any lesson
const memory = new Map<string, string>();

interface Stored<T> {
  value: T;
  savedAt: number;
}

function read(key: string): string | null {
  try {
    return localStorage.getItem(key) ?? memory.get(key) ?? null;
  } catch {
    return memory.get(key) ?? null;
  }
}

export function load<T>(key: string): T | null {
  const raw = read(key);
  if (!raw) return null;
  try {
    const stored = JSON.parse(raw) as Stored<T>;
    if (typeof stored?.savedAt !== "number" || Date.now() - stored.savedAt > MAX_AGE_MS) {
      clear(key);
      return null;
    }
    return stored.value;
  } catch {
    clear(key);
    return null;
  }
}

export function save(key: string, value: unknown) {
  const raw = JSON.stringify({ value, savedAt: Date.now() });
  memory.set(key, raw);
  try {
    localStorage.setItem(key, raw);
  } catch {
    /* memory copy is enough for this tab */
  }
}

export function clear(key: string) {
  memory.delete(key);
  try {
    localStorage.removeItem(key);
  } catch {
    /* ignore */
  }
}
