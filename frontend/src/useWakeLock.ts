import { useEffect } from "react";

/**
 * Keeps the screen on while `active` is true, so a phone does not lock (and
 * drop its connection) in the middle of a question. Browsers release the lock
 * when the page is hidden, so it is asked for again when the page comes back.
 * Where the browser does not support it, nothing happens.
 */
export function useWakeLock(active: boolean) {
  useEffect(() => {
    if (!active || !("wakeLock" in navigator)) return;
    let lock: WakeLockSentinel | null = null;
    let cancelled = false;

    const request = async () => {
      if (document.visibilityState !== "visible" || cancelled) return;
      try {
        lock = await navigator.wakeLock.request("screen");
      } catch {
        /* low battery mode or not allowed: the reconnect logic still covers us */
      }
    };
    void request();
    document.addEventListener("visibilitychange", request);

    return () => {
      cancelled = true;
      document.removeEventListener("visibilitychange", request);
      void lock?.release().catch(() => undefined);
    };
  }, [active]);
}
