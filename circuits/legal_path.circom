pragma circom 2.0.0;

/*
 * Legal-path proof: "I know an intermediate node `mid` such that
 * (start, mid) and (mid, goal) are both edges in the published
 * arena adjacency bitmap."
 *
 * This upgrades the toy `multiplier.circom` to a semantically
 * meaningful Penumbra demo: a real ZK proof that an agent took
 * legal moves through the arena, without revealing which
 * intermediate node it passed through.
 *
 * Layout (N = 4 here; N² = 16 adjacency bits)
 * ───────────────────────────────────────────
 *   Public inputs (in order):
 *     adj[0..15]   the arena adjacency bitmap (row-major).
 *                  adj[u*N + v] == 1 ⇔ edge (u,v) exists.
 *     start        the starting node id (private to the arena;
 *                  PUBLIC to the verifier).
 *     goal         the goal node id (PUBLIC).
 *   Private input:
 *     mid          the intermediate node the prover claims to
 *                  have visited.
 *
 * Constraints
 * ───────────
 *   1. Every adjacency entry must be 0 or 1 (binary).
 *   2. adj[start*N + mid]  must equal 1   (the first hop is legal).
 *   3. adj[mid*N + goal]   must equal 1   (the second hop is legal).
 *
 * The selectors (2) and (3) use circomlib's `IsEqual` to read a
 * signal-typed index out of a constant-length bitmap. For each of
 * the N² entries we compute `(idx == k) * adj[k]` and sum — the
 * result is `adj[idx]`. Cost: ~2 N² constraints per hop.
 *
 * Why 2 hops (and N=4)?
 * The point is to demonstrate the protocol shape without a giant
 * trusted-setup ptau. A 3-hop / 8-node version is the same
 * structure with bigger loops; circuits/setup.sh keeps the ptau
 * small enough to regenerate locally in seconds.
 */

include "circomlib/circuits/comparators.circom";

template AdjacencyBit(NN) {
    // NN = N*N. Outputs adj[idx] for a signal-typed `idx`.
    signal input adj[NN];
    signal input idx;
    signal output bit;

    component eqs[NN];
    var accum = 0;
    signal terms[NN];
    for (var k = 0; k < NN; k++) {
        eqs[k] = IsEqual();
        eqs[k].in[0] <== idx;
        eqs[k].in[1] <== k;
        terms[k] <== eqs[k].out * adj[k];
        accum += terms[k];
    }
    bit <== accum;
}

template LegalPath2Hop(N) {
    var NN = N * N;
    // Public:
    signal input adj[NN];
    signal input start;
    signal input goal;
    // Private:
    signal input mid;

    // (1) Each adj entry must be 0 or 1.
    for (var k = 0; k < NN; k++) {
        adj[k] * (adj[k] - 1) === 0;
    }

    // (2) First hop must be a real edge.
    component hop1 = AdjacencyBit(NN);
    for (var k = 0; k < NN; k++) {
        hop1.adj[k] <== adj[k];
    }
    hop1.idx <== start * N + mid;
    hop1.bit === 1;

    // (3) Second hop must be a real edge.
    component hop2 = AdjacencyBit(NN);
    for (var k = 0; k < NN; k++) {
        hop2.adj[k] <== adj[k];
    }
    hop2.idx <== mid * N + goal;
    hop2.bit === 1;
}

// N=4 nodes ⇒ 16-bit adjacency, ~64 selector constraints per hop.
component main {public [adj, start, goal]} = LegalPath2Hop(4);
