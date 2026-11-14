import { io } from "socket.io-client";

// Empty in development (same address, Vite proxies it). In production this is
// the backend address, e.g. https://api.example.com
const SERVER_URL = import.meta.env.VITE_SERVER_URL || undefined;

export const socket = io(SERVER_URL, {
  autoConnect: false,
  reconnection: true,
  reconnectionDelay: 800,
  reconnectionDelayMax: 4000,
  timeout: 10000,
  // Start with long-polling and upgrade to WebSocket: works on mobile networks
  // and school Wi-Fi that block WebSockets.
});

export class CallError extends Error {
  constructor(public code: string, message: string) {
    super(message);
  }
}

/**
 * Ask the server to do something and wait for its reply.
 * Never hangs: after 8 seconds it gives up with a clear message.
 */
export async function call<T = Record<string, unknown>>(
  event: string,
  data: Record<string, unknown> = {},
): Promise<T> {
  if (!socket.connected) {
    throw new CallError("offline", "Not connected to the quiz server. Reconnecting…");
  }
  let reply: { ok: boolean; error?: string; message?: string } & T;
  try {
    reply = await socket.timeout(8000).emitWithAck(event, data);
  } catch {
    throw new CallError("timeout", "The server took too long to reply. Please try again.");
  }
  if (!reply.ok) {
    throw new CallError(reply.error ?? "error", reply.message ?? "Something went wrong.");
  }
  return reply;
}
