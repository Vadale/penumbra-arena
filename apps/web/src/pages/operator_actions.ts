/**
 * Operator action metadata — UX layer over the backend action catalogue.
 *
 * Concept taught: the 20 operator action kinds exposed by
 * `packages/operator/penumbra_operator/actions.py` are bare backend
 * enums. A newcomer who picks `query_dp` from the dropdown otherwise
 * sees four empty inputs and earns themselves a 422. This module pairs
 * every kind with a one-line description, ghost-text placeholders that
 * match the validator's expected types, and a coarse "cost" hint.
 *
 * Field placeholders intentionally use numeric strings (e.g. "12", "0.5")
 * for fields the backend coerces to numbers — the Action Builder's
 * coercePayload() will turn them into the right JSON types before POST.
 *
 * Keep ACTION_KINDS in sync with `actions._HANDLERS`; the test suite
 * relies on the same ordering for the dropdown.
 */

export const ACTION_KINDS = [
  // ── Tier 1 core (8) ──
  "move",
  "buy",
  "sell",
  "dispatch_order",
  "cancel_assignment",
  "query_dp",
  "sign",
  "verify",
  // ── Tier 3 attacks (6) ──
  "attack_replay",
  "attack_byzantine",
  "attack_dp_recon",
  "attack_linkability",
  "attack_membership",
  "attack_snark_forge",
  // ── Tier 4 defenses (6) ──
  "defense_k_anonymity",
  "defense_padding",
  "defense_gan_poison",
  "defense_pause_dp",
  "defense_resume_dp",
  "defense_rotate_keys",
  "defense_enable_krum",
] as const;

export type ActionKind = (typeof ACTION_KINDS)[number];

export interface ActionMeta {
  /** Short human label shown next to the backend enum in the dropdown. */
  label: string;
  /** One-sentence description rendered as a caption below the dropdown. */
  description: string;
  /** Ghost-text per form field — strings so they render directly in <input>. */
  placeholders: Record<string, string>;
  /** Coarse cost hint ("free", "5 coins", "0.5 ε"). */
  coins_cost: string;
}

export const ACTION_META: Record<ActionKind, ActionMeta> = {
  // ── core ───────────────────────────────────────────────────────
  move: {
    label: "Move to a neighbour node",
    description: "Move the operator agent to an adjacent node on the arena graph.",
    placeholders: { target_node: "12" },
    coins_cost: "edge cost (coins)",
  },
  buy: {
    label: "Buy product at current node",
    description: "Buy `qty` units of `product` at the local market's ask price.",
    placeholders: { product: "0", qty: "5" },
    coins_cost: "ask price × qty",
  },
  sell: {
    label: "Sell inventory at current node",
    description: "Sell `qty` units of `product` to the local market at the bid price.",
    placeholders: { product: "0", qty: "5" },
    coins_cost: "free (revenue in)",
  },
  dispatch_order: {
    label: "Queue logistics order",
    description: "Place a delivery order to a remote city; carriers pick it up.",
    placeholders: { city: "3", product: "0", qty: "10", reward: "5.0" },
    coins_cost: "reward paid on fulfilment",
  },
  cancel_assignment: {
    label: "Release a pending order",
    description: "Unassign a pending logistics order so another carrier can pick it.",
    placeholders: { order_id: "1" },
    coins_cost: "free",
  },
  query_dp: {
    label: "Run a DP-noised query",
    description: "Run a Laplace-noised aggregate; consumes ε from the operator's budget.",
    placeholders: { statistic: "money_supply", epsilon: "0.1" },
    coins_cost: "ε from privacy budget",
  },
  sign: {
    label: "Sign a message (PQ)",
    description: "Sign a hex-encoded message with the operator's post-quantum keypair.",
    placeholders: { message: "deadbeef" },
    coins_cost: "free",
  },
  verify: {
    label: "Verify a PQ signature",
    description: "Verify a signature/message/public-key triple (all hex-encoded).",
    placeholders: { message: "deadbeef", sig: "<hex>", public_key: "<hex>" },
    coins_cost: "free",
  },
  // ── attacks ────────────────────────────────────────────────────
  attack_replay: {
    label: "Replay a captured signature",
    description: "Replay a captured signature against the naive vs tick-bound protocol.",
    placeholders: { target_signature_hex: "deadbeef", replay_offset: "1" },
    coins_cost: "free",
  },
  attack_byzantine: {
    label: "Equivocate as a validator",
    description: "Sign two conflicting blocks to demonstrate slashable equivocation.",
    placeholders: { n_equivocations: "2" },
    coins_cost: "free",
  },
  attack_dp_recon: {
    label: "DP reconstruction attack",
    description: "Run a Dinur-Nissim style reconstruction against a target's bits.",
    placeholders: { target_agent: "3", query_log: "[]" },
    coins_cost: "free",
  },
  attack_linkability: {
    label: "Link pseudonymous matches",
    description: "Try to link anonymous match aggregates back to a target agent.",
    placeholders: { feature_set: '["score","path_len"]', target_agent: "3" },
    coins_cost: "free",
  },
  attack_membership: {
    label: "Membership inference",
    description: "Decide if an observation was in the MAPPO actor's training set.",
    placeholders: { target_observation: "[0.1,0.2,0.3]" },
    coins_cost: "free",
  },
  attack_snark_forge: {
    label: "Forge a Groth16 proof",
    description: "Attempt to forge a SNARK proof for a named circuit (rejected by pairing).",
    placeholders: { circuit: "match_outcome" },
    coins_cost: "free",
  },
  // ── defenses ───────────────────────────────────────────────────
  defense_k_anonymity: {
    label: "Enable k-anonymity",
    description: "Require `k` agents per equivalence class before releasing `statistic`.",
    placeholders: { k: "5", statistic: "money_supply" },
    coins_cost: "free",
  },
  defense_padding: {
    label: "Enable request/response padding",
    description: "Pad request or response bodies to `size` bytes to blunt traffic analysis.",
    placeholders: { kind: "request", size: "256" },
    coins_cost: "free",
  },
  defense_gan_poison: {
    label: "Enable GAN-based poisoning defence",
    description: "Inject synthetic noise into `target_stat` at the configured `rate`.",
    placeholders: { rate: "0.1", target_stat: "price_index" },
    coins_cost: "free",
  },
  defense_pause_dp: {
    label: "Pause all DP queries",
    description: "Freeze the DP mechanism so no further ε is spent until resumed.",
    placeholders: {},
    coins_cost: "free",
  },
  defense_resume_dp: {
    label: "Resume DP queries",
    description: "Un-pause the DP mechanism and allow queries to consume ε again.",
    placeholders: {},
    coins_cost: "free",
  },
  defense_rotate_keys: {
    label: "Rotate signing keypair",
    description: "Generate a fresh PQ keypair for the operator and discard the old one.",
    placeholders: {},
    coins_cost: "free",
  },
  defense_enable_krum: {
    label: "Switch FL aggregator to Krum",
    description: "Use Krum (tolerates `f` byzantine clients) for federated aggregation.",
    placeholders: { f: "1" },
    coins_cost: "free",
  },
};

/** Fields that must be POSTed as numbers (the backend rejects strings). */
const NUMERIC_FIELDS: Record<ActionKind, ReadonlyArray<string>> = {
  move: ["target_node"],
  buy: ["product", "qty"],
  sell: ["product", "qty"],
  dispatch_order: ["city", "product", "qty", "reward"],
  cancel_assignment: ["order_id"],
  query_dp: ["epsilon"],
  sign: [],
  verify: [],
  attack_replay: ["replay_offset"],
  attack_byzantine: ["n_equivocations"],
  attack_dp_recon: ["target_agent"],
  attack_linkability: ["target_agent"],
  attack_membership: [],
  attack_snark_forge: [],
  defense_k_anonymity: ["k"],
  defense_padding: ["size"],
  defense_gan_poison: ["rate"],
  defense_pause_dp: [],
  defense_resume_dp: [],
  defense_rotate_keys: [],
  defense_enable_krum: ["f"],
};

/** Fields that must be POSTed as JSON-parsed values (arrays / objects). */
const JSON_FIELDS: Record<ActionKind, ReadonlyArray<string>> = {
  move: [],
  buy: [],
  sell: [],
  dispatch_order: [],
  cancel_assignment: [],
  query_dp: [],
  sign: [],
  verify: [],
  attack_replay: [],
  attack_byzantine: [],
  attack_dp_recon: ["query_log"],
  attack_linkability: ["feature_set"],
  attack_membership: ["target_observation"],
  attack_snark_forge: [],
  defense_k_anonymity: [],
  defense_padding: [],
  defense_gan_poison: [],
  defense_pause_dp: [],
  defense_resume_dp: [],
  defense_rotate_keys: [],
  defense_enable_krum: [],
};

/**
 * Build the empty form payload for `kind` — one key per editable field,
 * all values starting as empty strings. The field order is taken from
 * ACTION_META.placeholders so the dropdown's switch determines layout.
 */
export function emptyPayloadFor(kind: ActionKind): Record<string, string> {
  const out: Record<string, string> = {};
  for (const field of Object.keys(ACTION_META[kind].placeholders)) {
    out[field] = "";
  }
  return out;
}

/**
 * Coerce a string-keyed form payload into the JSON types each backend
 * handler expects (ints / floats / parsed JSON arrays). String fields
 * pass through unchanged.
 */
export function coercePayload(
  kind: ActionKind,
  raw: Record<string, string>,
): Record<string, unknown> {
  const numKeys = new Set<string>(NUMERIC_FIELDS[kind]);
  const jsonKeys = new Set<string>(JSON_FIELDS[kind]);
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(raw)) {
    if (numKeys.has(k)) {
      const n = Number(v);
      out[k] = Number.isFinite(n) ? n : 0;
    } else if (jsonKeys.has(k)) {
      try {
        out[k] = v.trim() === "" ? [] : JSON.parse(v);
      } catch {
        out[k] = [];
      }
    } else {
      out[k] = v;
    }
  }
  return out;
}
