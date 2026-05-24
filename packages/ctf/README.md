# penumbra-ctf

Capture-the-Flag harness for Penumbra. Each YAML challenge under
`challenges/` defines an `id`, a human title, a `setup` block whose
fields fix the attack scenario (DP epsilon, query budget, target
agent, etc.), an `acceptance` block describing what a winning
submission must show, and a `flag_template` whose placeholders are
filled by the harness after a winning submission.

Submissions land in a per-process leaderboard keyed by challenge id.
The first solver per `session_id` is recorded with a wall-clock
timestamp; later solvers stack underneath.
