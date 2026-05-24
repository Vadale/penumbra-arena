# penumbra-notebook

IPython magic commands to drive a running Penumbra arena from a notebook.

```python
%load_ext penumbra_notebook

%penumbra connect http://localhost:8000
%penumbra snapshot                # returns the current /state payload

%%penumbra attack
def policy(state, observation):
    return 0
```

The cell magic runs the body in the same sandbox the FastAPI
`/attacker/policy` endpoint uses: whitelisted builtins, numpy + math
only, and a 50 ms wall-clock per call.
