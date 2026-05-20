# penumbra-core

Pure domain. No I/O. The integration seam where every Penumbra pillar
ultimately meets on each simulation tick.

## Concept taught

- **`rng.py`** — centralised reproducibility. One env-seeded source fans out
  to `random`, `numpy`, `torch`, `jax`. *Concept:* multi-library RNG hygiene.
- **`arena.py`** — graph world with Ornstein-Uhlenbeck edge costs, migrating
  goals, weather. *Concept:* SDE-driven graph dynamics → no static shortest
  path.
- **`agent.py`, `match.py`, `simulation.py`** — agents, episodes, the
  perpetual tick loop. *Concept:* an "episode" is an artificial boundary on
  a continuous-time process; the simulation persists agents and stats
  across them.

## Micro-experiments

- Seed the RNG to two values, run 1000 ticks each, diff the agent
  trajectories. Identical seeds → identical trajectories.
- Halve the OU mean-reversion in `arena.py`; observe how edge-cost volatility
  affects coalition formation.

## Public API

```python
from penumbra_core.rng import bootstrap, run_record
from penumbra_core.arena import Arena, ArenaConfig
from penumbra_core.agent import Agent
from penumbra_core.match import Match
from penumbra_core.simulation import Simulation
```
