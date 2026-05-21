# penumbra-shell-coach

Curated macOS/Unix terminal tutor + command explainer + error helper.

## Concept taught

Three small primitives composed into a tutor:

- **`runner.py`** — YAML-driven lesson stepper. Each lesson is a
  sequence of `{instruction, validate_cmd, expected_pattern, hint}`
  steps; the runner re-executes `validate_cmd` and regex-checks the
  output before unlocking the next step. Destructive commands are
  blacklisted at the runner level.
- **`explain.py`** — static command-flag database (~10 binaries, ~60
  flags) + argv parsing. Knows how to decompose `ls -lah` into
  `-l`, `-a`, `-h` and explain each.
- **`suggester.py`** — rule-based "what to try next" suggestions
  keyed on the last command's binary. Maps classic Unix tools to
  modern replacements (`ls → eza`, `grep → rg`, `find → fd`, `cat → bat`).
- **`error_helper.py`** — regex → one-line fix mapping for the most
  common error messages (command-not-found, Permission denied,
  Address-already-in-use, ModuleNotFoundError, …).

## Lessons bundled (11 tracks)

1. filesystem · 2. text_processing · 3. pipes_redirection ·
4. networking_curl · 5. macos_specific · 6. modern_cli ·
7. processes · 8. archives · 9. permissions · 10. crypto_tools ·
11. scripting_hygiene.

## Micro-experiments

1. Step through a track:
   ```sh
   psh lessons          # list
   psh lesson crypto_tools
   ```
2. Use the explainer on an unfamiliar invocation:
   ```sh
   psh explain "curl -sIL https://example.com"
   ```
3. Paste an error and get a fix:
   ```sh
   psh interpret "zsh: command not found: rg"
   ```

## CLI

```sh
uv tool install ./packages/shell_coach
psh --help
psh {lessons,lesson <id>,explain "<cmd>",suggest <bin>,interpret "<stderr>"}
```
