/**
 * CKKS encrypt-decrypt round-trip with error visualisation.
 *
 * CKKS is APPROXIMATE homomorphic encryption — that's the headline.
 * We encrypt a known plaintext vector, decrypt it, and show:
 *   - plaintext (cyan bars)
 *   - decrypted (ember bars)
 *   - absolute error per slot
 * plus the ciphertext byte size and a short hex preview to make
 * the "ciphertexts are big and opaque" point concrete.
 */

import { useEffect, useState } from "react";

interface CKKSPayload {
  available: boolean;
  backend?: string;
  plaintext?: number[];
  decrypted?: number[];
  absolute_error?: number[];
  ciphertext_size_bytes?: number | null;
  ciphertext_preview_hex?: string | null;
}

export function CKKSCompareChart() {
  const [data, setData] = useState<CKKSPayload | null>(null);
  const [busy, setBusy] = useState(false);

  const grab = async () => {
    setBusy(true);
    try {
      const res = await fetch("/crypto/ckks/compare");
      if (res.ok) setData((await res.json()) as CKKSPayload);
    } catch {}
    setBusy(false);
  };

  useEffect(() => {
    void grab();
  }, []);

  if (!data || !data.available) {
    return (
      <div className="font-mono text-xs text-[color:var(--color-penumbra-muted)]">
        {busy ? "encrypting…" : "CKKS unavailable"}
      </div>
    );
  }
  const plain = data.plaintext ?? [];
  const dec = data.decrypted ?? [];
  const err = data.absolute_error ?? [];
  const maxAbs = Math.max(...plain.map((v) => Math.abs(v)), 1);
  const maxErr = Math.max(...err, 1e-12);

  return (
    <div className="font-mono space-y-3">
      <div className="grid grid-cols-4 gap-2 text-[10px]">
        <Stat label="backend" value={data.backend ?? "—"} accent />
        <Stat
          label="ct size"
          value={
            data.ciphertext_size_bytes
              ? `${(data.ciphertext_size_bytes / 1024).toFixed(1)} KB`
              : "n/a"
          }
          accent
        />
        <Stat label="slots" value={String(plain.length)} />
        <button
          type="button"
          onClick={grab}
          disabled={busy}
          className="border border-[color:var(--color-penumbra-cyan)] bg-[color:var(--color-penumbra-cyan-bg)] px-2 py-1 text-[10px] uppercase text-[color:var(--color-penumbra-cyan)] disabled:opacity-50"
        >
          {busy ? "encrypting…" : "re-encrypt"}
        </button>
      </div>

      <div>
        <div className="mb-1 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
          plaintext (cyan) vs decrypted (ember) — should overlap modulo small error
        </div>
        <svg
          viewBox={`0 0 560 ${plain.length * 22 + 6}`}
          width="100%"
          role="img"
          aria-label="ckks roundtrip"
        >
          {plain.map((p, i) => {
            const y = i * 22 + 4;
            const wP = (Math.abs(p) / maxAbs) * 240;
            const d = dec[i] ?? 0;
            const wD = (Math.abs(d) / maxAbs) * 240;
            return (
              <g key={`slot-${i}-${p.toFixed(4)}`}>
                <rect
                  x={120}
                  y={y}
                  width={Math.max(1, wP)}
                  height={8}
                  fill="var(--color-penumbra-cyan)"
                  opacity={0.7}
                />
                <rect
                  x={120}
                  y={y + 10}
                  width={Math.max(1, wD)}
                  height={8}
                  fill="var(--color-penumbra-ember)"
                  opacity={0.7}
                />
                <text x={6} y={y + 8} fontSize={9} fill="var(--color-penumbra-muted)">
                  slot {i}
                </text>
                <text
                  x={368}
                  y={y + 8}
                  fontSize={9}
                  fill="var(--color-penumbra-text)"
                  textAnchor="end"
                >
                  {p.toFixed(2)} / {d.toFixed(4)}
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      <div>
        <div className="mb-1 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
          absolute error per slot · max = {maxErr.toExponential(2)}
        </div>
        <svg viewBox={`0 0 560 24`} width="100%" role="img" aria-label="ckks error">
          {err.map((e, i) => {
            const x = (i / Math.max(err.length, 1)) * 540;
            const h = (e / maxErr) * 20;
            return (
              <rect
                key={`err-${i}-${e.toExponential(2)}`}
                x={x}
                y={22 - h}
                width={540 / err.length - 1}
                height={h}
                fill="color-mix(in srgb, var(--color-penumbra-ember) 60%, transparent)"
              />
            );
          })}
        </svg>
      </div>

      {data.ciphertext_preview_hex && (
        <div>
          <div className="mb-1 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
            ciphertext (first 32 bytes hex)
          </div>
          <div className="border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] p-2 text-[10px] text-[color:var(--color-penumbra-cyan)] break-all">
            {data.ciphertext_preview_hex}…
          </div>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-2 py-1">
      <div className="text-[8px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
        {label}
      </div>
      <div
        className={`tabular-nums ${accent ? "text-[color:var(--color-penumbra-cyan)]" : "text-[color:var(--color-penumbra-text)]"}`}
      >
        {value}
      </div>
    </div>
  );
}
