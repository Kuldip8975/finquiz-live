import { useEffect, useRef, useState } from "react";
import { socket } from "./socket";

export type ConnectionStatus = "connecting" | "online" | "reconnecting" | "failed";

const GIVE_UP_MS = 15000;

/**
 * Connects the socket and reports its status so the page can show a banner.
 *
 * `onConnect` runs on the first connection AND after every reconnection.
 * That matters: after a drop the server sees a brand-new connection, so the
 * page must tell it again who it is (resume with the saved token).
 *
 * Phones pause pages that are in the background (another app opened, screen
 * locked). When the page comes back we do not wait for the socket to notice
 * on its own: we reconnect at once, or re-sync if it is still connected.
 */
export function useConnection(onConnect: () => void) {
  const [status, setStatus] = useState<ConnectionStatus>("connecting");
  const onConnectRef = useRef(onConnect);
  onConnectRef.current = onConnect;
  const giveUpTimer = useRef<ReturnType<typeof setTimeout>>();

  const startGiveUpTimer = () => {
    clearTimeout(giveUpTimer.current);
    giveUpTimer.current = setTimeout(() => {
      if (!socket.connected) setStatus("failed");
    }, GIVE_UP_MS);
  };

  useEffect(() => {
    const handleConnect = () => {
      clearTimeout(giveUpTimer.current);
      setStatus("online");
      onConnectRef.current();
    };
    const handleDisconnect = () => {
      setStatus("reconnecting");
      startGiveUpTimer();
    };
    const handleComeBack = () => {
      if (document.visibilityState === "hidden") return;
      if (socket.connected) {
        onConnectRef.current(); // re-sync: we may have missed updates while paused
      } else {
        setStatus("reconnecting");
        socket.connect();
        startGiveUpTimer();
      }
    };

    socket.on("connect", handleConnect);
    socket.on("disconnect", handleDisconnect);
    document.addEventListener("visibilitychange", handleComeBack);
    window.addEventListener("online", handleComeBack);
    window.addEventListener("pageshow", handleComeBack);
    socket.connect();
    startGiveUpTimer();

    return () => {
      clearTimeout(giveUpTimer.current);
      socket.off("connect", handleConnect);
      socket.off("disconnect", handleDisconnect);
      document.removeEventListener("visibilitychange", handleComeBack);
      window.removeEventListener("online", handleComeBack);
      window.removeEventListener("pageshow", handleComeBack);
      socket.disconnect();
    };
  }, []);

  const retry = () => {
    setStatus("connecting");
    socket.disconnect();
    socket.connect();
    startGiveUpTimer();
  };

  return { status, retry };
}
