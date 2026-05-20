import { decode } from "@msgpack/msgpack";
import { useEffect } from "react";
import { isTickFrame } from "./frames";
import { usePenumbraStore } from "./store";

/**
 * WebSocket client hook.
 *
 * Concept taught: useEffect with a stable URL handles reconnects via a
 * setTimeout backoff. msgpack-decode each binary frame and validate the
 * shape before pushing into the zustand store.
 */

const WS_URL = `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}/ws`;
const RECONNECT_DELAY_MS = 1_500;

export function usePenumbraSocket(): void {
  useEffect(() => {
    let socket: WebSocket | null = null;
    let reconnectTimer: number | null = null;
    let disposed = false;

    const setConnected = usePenumbraStore.getState().setConnected;
    const ingestFrame = usePenumbraStore.getState().ingestFrame;

    const connect = () => {
      if (disposed) return;
      socket = new WebSocket(WS_URL);
      socket.binaryType = "arraybuffer";

      socket.addEventListener("open", () => setConnected(true));
      socket.addEventListener("close", () => {
        setConnected(false);
        if (disposed) return;
        reconnectTimer = window.setTimeout(connect, RECONNECT_DELAY_MS);
      });
      socket.addEventListener("error", () => socket?.close());
      socket.addEventListener("message", (event) => {
        if (!(event.data instanceof ArrayBuffer)) return;
        const payload = decode(new Uint8Array(event.data));
        if (isTickFrame(payload)) {
          ingestFrame(payload);
        }
      });
    };

    connect();

    return () => {
      disposed = true;
      if (reconnectTimer !== null) window.clearTimeout(reconnectTimer);
      socket?.close();
    };
  }, []);
}
