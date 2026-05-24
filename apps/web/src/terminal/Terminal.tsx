/**
 * xterm.js PTY-backed terminal panel.
 *
 * Connects to /ws/pty on the backend (which spawns a real macOS zsh
 * under a pseudo-terminal). Bidirectional: keystrokes → PTY stdin,
 * PTY stdout/stderr → xterm.js draw.
 *
 * Gated by /pty/status — when PENUMBRA_ENABLE_PTY isn't set
 * server-side, we render a small explanatory placeholder instead of
 * trying to open the websocket (which would just close 4403).
 */

import { FitAddon } from "@xterm/addon-fit";
import { WebLinksAddon } from "@xterm/addon-web-links";
import { Terminal as XTerm } from "@xterm/xterm";
import "@xterm/xterm/css/xterm.css";
import { useEffect, useRef, useState } from "react";

// Use SAME-ORIGIN URLs everywhere; Vite proxies `/pty` + `/ws` to the
// backend in dev (config picks up PENUMBRA_API_PORT). In production
// the bundle is served by the same backend, so the relative paths
// hit the same host:port directly.
const PTY_WS_URL = (() => {
  if (typeof window === "undefined") return "";
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/ws/pty`;
})();

const PTY_STATUS_URL = "/pty/status";

export function Terminal() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [enabled, setEnabled] = useState<boolean | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch(PTY_STATUS_URL)
      .then((r) => r.json())
      .then((d: { enabled: boolean }) => {
        if (!cancelled) setEnabled(d.enabled);
      })
      .catch(() => {
        if (!cancelled) setEnabled(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (enabled !== true) return;
    if (!containerRef.current) return;

    const term = new XTerm({
      fontFamily: '"SF Mono", Menlo, Consolas, monospace',
      fontSize: 12,
      theme: { background: "#0f172a", foreground: "#e2e8f0" },
      cursorBlink: true,
      convertEol: true,
    });
    const fit = new FitAddon();
    term.loadAddon(fit);
    term.loadAddon(new WebLinksAddon());
    term.open(containerRef.current);
    fit.fit();

    const ws = new WebSocket(PTY_WS_URL);
    ws.binaryType = "arraybuffer";

    const sendResize = () => {
      if (ws.readyState !== WebSocket.OPEN) return;
      ws.send(
        JSON.stringify({
          type: "resize",
          rows: term.rows,
          cols: term.cols,
        }),
      );
    };

    ws.onopen = () => {
      sendResize();
      term.writeln(
        "\x1b[36m==> penumbra-shell\x1b[0m  type `psh lessons` to start tutorials, `pna --help` for attacks, `pno --help` for the operator console",
      );
    };
    ws.onmessage = (event) => {
      if (event.data instanceof ArrayBuffer) {
        term.write(new Uint8Array(event.data));
      } else if (typeof event.data === "string") {
        term.write(event.data);
      }
    };
    ws.onclose = () => {
      term.write("\r\n\x1b[31m[connection closed]\x1b[0m\r\n");
    };

    const onData = term.onData((data) => {
      if (ws.readyState !== WebSocket.OPEN) return;
      ws.send(JSON.stringify({ type: "input", data }));
    });

    const onResize = () => {
      fit.fit();
      sendResize();
    };
    window.addEventListener("resize", onResize);

    return () => {
      onData.dispose();
      window.removeEventListener("resize", onResize);
      ws.close();
      term.dispose();
    };
  }, [enabled]);

  if (enabled === null) {
    return <div className="text-xs text-slate-500">checking PTY availability…</div>;
  }
  if (enabled === false) {
    return (
      <div className="rounded border border-slate-800 bg-slate-900/40 p-3 text-xs text-slate-400">
        <div className="mb-1 text-slate-300">PTY shell disabled</div>
        <p>
          Set <code className="font-mono text-slate-200">PENUMBRA_ENABLE_PTY=1</code> in the backend
          environment to enable a real macOS <code className="font-mono">zsh</code> in this panel.
          The Coach panel above runs <code className="font-mono">pna</code> and{" "}
          <code className="font-mono">psh</code> under an allow-list — use it for restricted
          experiments.
        </p>
      </div>
    );
  }
  return <div ref={containerRef} className="h-full w-full" />;
}
