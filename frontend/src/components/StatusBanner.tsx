import type { ConnectionStatus } from "../useConnection";

/** Always tells the user what the connection is doing. Never a silent freeze. */
export function StatusBanner({ status, retry }: { status: ConnectionStatus; retry: () => void }) {
  if (status === "online") return null;
  if (status === "failed") {
    return (
      <div className="banner banner-error" role="alert">
        <span>Can't reach the quiz server. Check your internet connection.</span>
        <button onClick={retry}>Retry</button>
      </div>
    );
  }
  return (
    <div className="banner" role="status">
      <span className="spinner" aria-hidden />
      <span>{status === "connecting" ? "Connecting…" : "Connection lost. Reconnecting…"}</span>
    </div>
  );
}
