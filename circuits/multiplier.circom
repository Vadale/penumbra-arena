pragma circom 2.0.0;

/*
 * The hello-world of Groth16 circuits.
 *
 * Statement: "I know two field elements a and b such that a * b = c",
 * where c is public.
 *
 * Witness:  a, b   (private; the prover keeps them secret)
 * Public:   c      (the product; visible to the verifier)
 *
 * After compilation:
 *   - witness gen consumes inputs/sample.json {a, b} and writes
 *     witness.wtns + public.json (which contains [c]).
 *   - Penumbra's snark.verify(vk, proof, [c]) ?= True.
 */

template Multiplier() {
    signal input a;
    signal input b;
    signal output c;
    c <== a * b;
}

component main = Multiplier();
