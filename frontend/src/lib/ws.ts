/**
 * Reconnecting WebSocket client for `/api/v1/ws`.
 *
 * A single instance is shared by the whole app (see `store/app.tsx`). Consumers
 * subscribe to server event names (`message.created`, `conversation.updated`, …)
 * or to the pseudo events `"*"` (every payload) and `"status"` (connection
 * state changes).
 */
import { API_BASE, getToken } from "./api";
import type { RealtimeEnvelope } from "./types";

export type ConnectionState = "connecting" | "open" | "closed";
type Handler = (data: any, event: string) => void;

const PING_INTERVAL = 25_000;
const MAX_BACKOFF = 15_000;

export class RealtimeClient {
  private socket: WebSocket | null = null;
  private handlers = new Map<string, Set<Handler>>();
  private attempts = 0;
  private pingTimer: ReturnType<typeof setInterval> | null = null;
  private retryTimer: ReturnType<typeof setTimeout> | null = null;
  private stopped = true;

  /** Current connection state, mirrored to `"status"` subscribers. */
  state: ConnectionState = "closed";

  /** Open the socket (idempotent) and keep it open until {@link stop}. */
  start(): void {
    this.stopped = false;
    this.connect();
  }

  /** Close the socket and cancel any pending reconnection. */
  stop(): void {
    this.stopped = true;
    this.clearTimers();
    const socket = this.socket;
    this.socket = null;
    if (socket) {
      socket.onclose = null;
      socket.onerror = null;
      socket.onmessage = null;
      socket.onopen = null;
      try {
        socket.close();
      } catch {
        /* already closing */
      }
    }
    this.setState("closed");
  }

  /** Subscribe to an event name; returns the unsubscribe function. */
  on(event: string, handler: Handler): () => void {
    let set = this.handlers.get(event);
    if (!set) {
      set = new Set();
      this.handlers.set(event, set);
    }
    set.add(handler);
    return () => {
      set!.delete(handler);
      if (!set!.size) this.handlers.delete(event);
    };
  }

  /** Send a JSON frame if the socket is open. */
  send(payload: unknown): void {
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify(payload));
    }
  }

  /* ------------------------------------------------------------ internals */

  private url(): string {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const token = getToken();
    const query = token ? `?token=${encodeURIComponent(token)}` : "";
    return `${protocol}//${window.location.host}${API_BASE}/ws${query}`;
  }

  private connect(): void {
    if (this.stopped) return;
    if (this.socket && this.socket.readyState <= WebSocket.OPEN) return;

    this.setState("connecting");
    let socket: WebSocket;
    try {
      socket = new WebSocket(this.url());
    } catch {
      this.scheduleRetry();
      return;
    }
    this.socket = socket;

    socket.onopen = () => {
      this.attempts = 0;
      this.setState("open");
      this.clearPing();
      this.pingTimer = setInterval(() => this.send({ type: "ping" }), PING_INTERVAL);
    };

    socket.onmessage = (raw) => {
      let payload: RealtimeEnvelope | { type?: string };
      try {
        payload = JSON.parse(raw.data as string);
      } catch {
        return;
      }
      if ((payload as { type?: string }).type) return; // pong / control frames
      const envelope = payload as RealtimeEnvelope;
      if (!envelope.event) return;
      this.emit(envelope.event, envelope.data);
      this.emit("*", envelope);
    };

    socket.onerror = () => {
      /* `onclose` always follows — retry logic lives there. */
    };

    socket.onclose = () => {
      this.clearPing();
      if (this.socket === socket) this.socket = null;
      this.setState("closed");
      this.scheduleRetry();
    };
  }

  private scheduleRetry(): void {
    if (this.stopped || this.retryTimer) return;
    this.attempts += 1;
    const delay = Math.min(MAX_BACKOFF, 500 * 2 ** Math.min(this.attempts, 5));
    const jitter = Math.random() * 250;
    this.retryTimer = setTimeout(() => {
      this.retryTimer = null;
      this.connect();
    }, delay + jitter);
  }

  private emit(event: string, data: any): void {
    for (const handler of this.handlers.get(event) ?? []) {
      try {
        handler(data, event);
      } catch (error) {
        console.error("realtime handler failed", event, error);
      }
    }
  }

  private setState(state: ConnectionState): void {
    if (this.state === state) return;
    this.state = state;
    this.emit("status", state);
  }

  private clearPing(): void {
    if (this.pingTimer) clearInterval(this.pingTimer);
    this.pingTimer = null;
  }

  private clearTimers(): void {
    this.clearPing();
    if (this.retryTimer) clearTimeout(this.retryTimer);
    this.retryTimer = null;
  }
}

/** Process-wide realtime connection. */
export const realtime = new RealtimeClient();

export default realtime;
