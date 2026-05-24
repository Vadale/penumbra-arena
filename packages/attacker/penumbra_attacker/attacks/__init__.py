"""Adversarial attack catalogue against Penumbra's privacy surfaces.

Concept taught: the *defender's* job is to know every attack their
threat model is supposed to resist — so every module in this package
implements a working attack *and* names the mitigation that closes
it. Reading any module top-to-bottom answers: how does the attack
work, why does Penumbra resist it, what would break the defence.
"""
