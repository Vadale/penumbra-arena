/**
 * Federated Learning status tile.
 *
 * Renders the trainer summary (method, participants, rounds, recent
 * bandwidth and aggregation times) and exposes start/stop/round/
 * dp/method controls.
 */

import { useEffect, useState } from "react";
import { Stat } from "./_shared";

interface RecentRound {
  round_id: number;
  encrypted: boolean;
  method: string;
  bandwidth_bytes: number;
  aggregation_time_ms: number;
  l2_change: number;
}

interface Payload {
  available: boolean;
  enabled?: boolean;
  method?: string;
  n_participants?: number;
  rounds_completed?: number;
  local_steps_per_round?: number;
  dp_noise_sigma?: number;
  dp_l2_clip?: number;
  fedprox_mu?: number;
  topk_fraction?: number;
  quantize_bits?: number;
  personalised?: boolean;
  recent_rounds?: RecentRound[];
  reason?: string;
}

interface PrivacyPayload {
  available: boolean;
  epsilon: number;
  delta: number;
  n_steps_accounted: number;
  mode: "rdp" | "toy";
}

export function FederatedStatusChart() {
  const [data, setData] = useState<Payload | null>(null);
  const [privacy, setPrivacy] = useState<PrivacyPayload | null>(null);
  const [busy, setBusy] = useState(false);
  const [method, setMethod] = useState("fedavg");
  const [sigma, setSigma] = useState(0);
  const [clip, setClip] = useState(0);
  const [fedproxMu, setFedproxMu] = useState(0);
  const [topk, setTopk] = useState(1);

  const load = async () => {
    try {
      const res = await fetch("/federated/status");
      if (res.ok) setData((await res.json()) as Payload);
    } catch {}
    try {
      const pres = await fetch("/federated/privacy?delta=1e-5");
      if (pres.ok) setPrivacy((await pres.json()) as PrivacyPayload);
    } catch {}
  };

  useEffect(() => {
    void load();
    const h = window.setInterval(load, 5000);
    return () => window.clearInterval(h);
  }, []);

  const post = async (path: string, params?: Record<string, string | number>) => {
    setBusy(true);
    const qs = params
      ? "?" +
        Object.entries(params)
          .map(([k, v]) => `${k}=${v}`)
          .join("&")
      : "";
    try {
      await fetch(`${path}${qs}`, { method: "POST" });
      await load();
    } catch {}
    setBusy(false);
  };

  if (!data) {
    return (
      <div className="font-mono text-xs text-[color:var(--color-penumbra-muted)]">loading…</div>
    );
  }
  if (!data.available) {
    return (
      <div className="font-mono space-y-3">
        <div className="text-xs text-[color:var(--color-penumbra-muted)]">
          FL trainer not started ({data.reason ?? "no reason"})
        </div>
        <div className="grid grid-cols-3 gap-2 text-[10px] items-end">
          <label className="flex flex-col">
            <span className="text-[8px] uppercase text-[color:var(--color-penumbra-dim)]">
              method
            </span>
            <select
              value={method}
              onChange={(e) => setMethod(e.target.value)}
              className="bg-[color:var(--color-penumbra-bg)] border border-[color:var(--color-penumbra-border)] px-1 py-1 text-[10px]"
            >
              <option value="fedavg">FedAvg</option>
              <option value="ckks_sum">CKKS sum (encrypted)</option>
              <option value="krum">Krum (Byzantine-robust)</option>
              <option value="trimmed_mean">Trimmed mean</option>
            </select>
          </label>
          <button
            type="button"
            disabled={busy}
            onClick={() => post("/federated/start", { method })}
            className="border border-[color:var(--color-penumbra-cyan)] bg-[color:var(--color-penumbra-cyan-bg)] px-2 py-1 text-[10px] uppercase text-[color:var(--color-penumbra-cyan)] disabled:opacity-50"
          >
            {busy ? "starting…" : "start"}
          </button>
        </div>
      </div>
    );
  }
  return (
    <div className="font-mono space-y-3">
      <div className="grid grid-cols-4 gap-2 text-[10px]">
        <Stat label="method" value={data.method ?? "—"} accent />
        <Stat label="participants" value={data.n_participants ?? 0} />
        <Stat label="rounds" value={data.rounds_completed ?? 0} />
        <Stat label="enabled" value={data.enabled ? "yes" : "no"} accent={Boolean(data.enabled)} />
      </div>
      <div className="grid grid-cols-3 gap-2 text-[10px]">
        <Stat
          label={`RDP ε (δ=${(privacy?.delta ?? 1e-5).toExponential(0)})`}
          value={privacy?.epsilon ?? 0}
          digits={3}
          accent={Boolean(privacy && privacy.mode === "rdp")}
        />
        <Stat label="RDP steps" value={privacy?.n_steps_accounted ?? 0} />
        <Stat label="DP mode" value={privacy?.mode ?? "toy"} />
      </div>
      <div className="grid grid-cols-4 gap-2 text-[10px] items-end">
        <label className="flex flex-col">
          <span className="text-[8px] uppercase text-[color:var(--color-penumbra-dim)]">
            switch method
          </span>
          <select
            value={data.method ?? "fedavg"}
            onChange={async (e) => {
              setBusy(true);
              try {
                await fetch(`/federated/method/${e.target.value}`, { method: "POST" });
                await load();
              } catch {}
              setBusy(false);
            }}
            className="bg-[color:var(--color-penumbra-bg)] border border-[color:var(--color-penumbra-border)] px-1 py-1 text-[10px]"
          >
            <option value="fedavg">FedAvg</option>
            <option value="ckks_sum">CKKS sum</option>
            <option value="krum">Krum</option>
            <option value="trimmed_mean">Trimmed mean</option>
          </select>
        </label>
        <button
          type="button"
          disabled={busy}
          onClick={() => post("/federated/round")}
          className="border border-[color:var(--color-penumbra-cyan)] bg-[color:var(--color-penumbra-cyan-bg)] px-2 py-1 text-[10px] uppercase text-[color:var(--color-penumbra-cyan)] disabled:opacity-50"
        >
          {busy ? "…" : "run round"}
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => post("/federated/stop")}
          className="border border-[color:var(--color-penumbra-ember)] bg-[color:var(--color-penumbra-ember-bg)] px-2 py-1 text-[10px] uppercase text-[color:var(--color-penumbra-ember)] disabled:opacity-50"
        >
          stop
        </button>
        <Stat
          label="ε per step"
          value={
            (data.dp_l2_clip ?? 0) > 0 && (data.dp_noise_sigma ?? 0) > 0
              ? (data.dp_l2_clip ?? 0) / (data.dp_noise_sigma ?? 1)
              : 0
          }
          digits={3}
        />
      </div>
      <div className="grid grid-cols-3 gap-2 text-[10px] items-end">
        <label className="flex flex-col">
          <span className="text-[8px] uppercase text-[color:var(--color-penumbra-dim)]">DP σ</span>
          <input
            type="number"
            step="0.1"
            min={0}
            value={sigma}
            onChange={(e) => setSigma(Number(e.target.value))}
            className="bg-[color:var(--color-penumbra-bg)] border border-[color:var(--color-penumbra-border)] px-1 py-1 text-[10px]"
          />
        </label>
        <label className="flex flex-col">
          <span className="text-[8px] uppercase text-[color:var(--color-penumbra-dim)]">
            DP clip
          </span>
          <input
            type="number"
            step="0.1"
            min={0}
            value={clip}
            onChange={(e) => setClip(Number(e.target.value))}
            className="bg-[color:var(--color-penumbra-bg)] border border-[color:var(--color-penumbra-border)] px-1 py-1 text-[10px]"
          />
        </label>
        <button
          type="button"
          disabled={busy}
          onClick={() => post("/federated/dp", { sigma, clip })}
          className="border border-[color:var(--color-penumbra-cyan)] bg-[color:var(--color-penumbra-cyan-bg)] px-2 py-1 text-[10px] uppercase text-[color:var(--color-penumbra-cyan)] disabled:opacity-50"
        >
          apply DP
        </button>
      </div>
      <div className="grid grid-cols-3 gap-2 text-[10px] items-end">
        <label className="flex flex-col">
          <span className="text-[8px] uppercase text-[color:var(--color-penumbra-dim)]">
            FedProx μ
          </span>
          <input
            type="number"
            step="0.001"
            min={0}
            value={fedproxMu}
            onChange={(e) => setFedproxMu(Number(e.target.value))}
            className="bg-[color:var(--color-penumbra-bg)] border border-[color:var(--color-penumbra-border)] px-1 py-1 text-[10px]"
          />
        </label>
        <label className="flex flex-col">
          <span className="text-[8px] uppercase text-[color:var(--color-penumbra-dim)]">
            top-k frac
          </span>
          <input
            type="number"
            step="0.05"
            min={0}
            max={1}
            value={topk}
            onChange={(e) => setTopk(Number(e.target.value))}
            className="bg-[color:var(--color-penumbra-bg)] border border-[color:var(--color-penumbra-border)] px-1 py-1 text-[10px]"
          />
        </label>
        <button
          type="button"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            try {
              await fetch(`/federated/fedprox?mu=${fedproxMu}`, { method: "POST" });
              await fetch(`/federated/compress?topk=${topk}&quantize=0`, { method: "POST" });
              await load();
            } catch {}
            setBusy(false);
          }}
          className="border border-[color:var(--color-penumbra-cyan)] bg-[color:var(--color-penumbra-cyan-bg)] px-2 py-1 text-[10px] uppercase text-[color:var(--color-penumbra-cyan)] disabled:opacity-50"
        >
          apply tier5
        </button>
      </div>
      <div className="grid grid-cols-3 gap-2 text-[10px]">
        <Stat label="FedProx μ" value={data.fedprox_mu ?? 0} digits={4} />
        <Stat label="top-k" value={data.topk_fraction ?? 1} digits={3} />
        <Stat
          label="personalised"
          value={data.personalised ? "yes" : "no"}
          accent={Boolean(data.personalised)}
        />
      </div>
      <div className="text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
        Recent rounds
      </div>
      <ul className="text-[10px] space-y-1">
        {(data.recent_rounds ?? []).slice(-5).map((r) => (
          <li key={`r-${r.round_id}`}>
            #{r.round_id} · {r.method}
            {r.encrypted ? " 🔒" : ""} · {(r.bandwidth_bytes / 1024).toFixed(1)} KiB ·{" "}
            {r.aggregation_time_ms.toFixed(1)} ms · Δw {r.l2_change.toFixed(4)}
          </li>
        ))}
      </ul>
    </div>
  );
}
