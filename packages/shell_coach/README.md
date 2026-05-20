# penumbra-shell-coach

Curated macOS/Unix terminal tutor.

## Quickstart

```sh
uv tool install ./packages/shell_coach
psh lessons              # list curricula
psh lesson filesystem    # step through a track
psh explain ls -la       # break down a command
psh suggest 'ls | wc -l' # rule-based next-command suggestion
```

## Content

6 starter tracks covering the most useful day-to-day Mac/Unix surface:

1. `filesystem`         — ls/find/mdfind/stat/du/tree/eza
2. `text_processing`    — grep/rg/awk/sed/cut/sort/uniq/tr
3. `pipes_redirection`  — |/>/2>/<<</tee/process substitution
4. `networking_curl`    — curl/wget/dig/nc/httpie
5. `macos_specific`     — brew/launchctl/defaults/pbcopy/mdfind/open
6. `modern_cli`         — rg/bat/eza/fzf/zoxide/jq/yq

## Concept taught

Each lesson is a sequence of `{instruction, validate_cmd,
expected_pattern, hint}` steps. The user runs the command in any
terminal (or the dashboard's PTY panel in Phase 7); the lesson
runner re-executes `validate_cmd` and checks `expected_pattern`
before unlocking the next step.

`explain` reads argv and looks up flag descriptions from a curated
database of ~30 common commands. `suggest` uses a small rule book
to point at the next useful command after what you just ran.
