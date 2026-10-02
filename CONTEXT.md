# Project Context — Smart Auto Typer

Context for future work on this project. For usage, see `README.md`.

## What this is

A single-file Python script (`ollama_typer.py`) that types a message for the user in
their own writing style, like a human (variable speed, pauses, typos it corrects). It
was deliberately simplified from a heavily-flagged version to a **no-flags, linear
flow**: read `message.txt`, humanize using `style.txt`, write `humanized.txt`, let the
user edit it and press `y`, ask for a WPM (default 120), then type.

## Environment

- **Working dir:** `/Users/aryan/customApps/smartautotyper`
- **Python:** use `.venv/` (built on **python3.12**). Homebrew's **Python 3.14 is broken**
  on this machine — `pip`/`pyexpat` crash with a missing `_XML_Set...` symbol. Do not
  use `python3`/3.14 here. (Pylance may warn it can't resolve `requests`/`pynput` — false
  positive; the editor isn't pointed at `.venv`.)
- **Ollama:** Ubuntu box `192.168.4.50`, user `sithoreo`. Ollama is bound to localhost
  on the box (NOT exposed on the LAN, by choice — see security decision below). The
  script reaches it via an **auto SSH tunnel** using dedicated key `~/.ssh/id_ollama`
  (passwordless). Model `llama3.1:8b-instruct-q8_0` (bare `llama3.1` tag does not exist
  on the box).
- **macOS Accessibility** permission is required for `pynput` keystrokes.
- **Alias:** `aiat` in `~/.zshrc` just runs the script (no flags).

## Key decisions

- **No flags / simple flow** (latest user direction): the earlier flag-heavy design was
  too complicated. Fixed file names (`message.txt`, `style.txt`, `humanized.txt`) in the
  script's own folder; all behavior (typos, pauses, thinking hesitations) is always on.
- **`pynput`** (not pyautogui) — finer control for char-level typos/backspace.
- **Light humanize, not heavy rewrite.** The model over-dramatized and leaked sample
  content; the prompt is strict: preserve meaning/structure, no preamble, don't borrow
  from the style sample. `strip_preamble()` is a backstop.
- **Connectivity = auto SSH tunnel, not LAN exposure.** Ollama has no auth, so binding
  it to `0.0.0.0` would let anyone on the LAN use/delete models. Tunnel keeps Ollama on
  localhost; traffic rides encrypted SSH. Auto-opened by `open_tunnel`, torn down via
  `atexit`.
- **Dedicated SSH key `~/.ssh/id_ollama`** (not the GitHub/default key, per user
  request). No-passphrase so the tunnel runs unattended; public key installed on the
  box. The user's SSH password is NOT stored anywhere.

## Architecture (`ollama_typer.py`)

- Constants at top: `MODEL`, `DEFAULT_WPM=120`, `TYPO_RATE=0.02`, SSH/tunnel settings.
- `open_tunnel` / `_port_open` — open+reuse the SSH tunnel, return the base URL.
- `ollama` — single `/api/generate` POST.
- `humanize` / `strip_preamble` — light style rewrite.
- `maybe_typo` — adjacent-QWERTY or doubled-letter typo.
- `to_sentences` / `parse_json` / `generate_false_starts` — split text into
  paragraphs→sentences; ask the AI (one call, JSON) for short alternative openings for
  up to `MAX_FALSE_STARTS` (4) sentences. Best-effort: empty dict if the call fails
  (caught in `main`). Verified live: produces plausible same-idea openings.
- `type_like_human` — `pynput` typing, sentence by sentence: WPM jitter, punctuation
  slowdowns, paragraph pauses (1.5–3.5s), typo→backspace→retype (~2%), ~8% thinking
  hesitations, and **false starts** (type an alternative opening with `type_plain`,
  pause, backspace it, then type the real sentence) — the "changed my mind" effect.
- `main()` — read files → tunnel → humanize → write humanized.txt → y/r/q prompt →
  ask WPM → 5s countdown → type.

## Verified

- Syntax OK; live end-to-end run: tunnel connected, message humanized, `humanized.txt`
  written, prompt quit cleanly (`q`). Humanized output faithful, no preamble/leakage.

## Not yet verified / open items

- Real keystroke output into a target app (needs Accessibility grant).
- `style.txt` was seeded by copying `~/my_style.txt`; the latter is now redundant.

## Files

- `ollama_typer.py` — the tool (no flags)
- `message.txt` — user's input message
- `style.txt` — user's writing sample
- `humanized.txt` — generated output (editable before typing)
- `requirements.txt` — `pynput`, `requests`
- `README.md` — usage / setup
- `CONTEXT.md` — this file
- `.venv/` — local virtualenv (python3.12)
