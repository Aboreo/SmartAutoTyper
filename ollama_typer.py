#!/usr/bin/env python3
"""
Smart Auto Typer — no flags, just run it.

Flow:
    1. You write your message in   message.txt
    2. It reads your style from     style.txt
    3. It humanizes the message and writes it to   humanized.txt
    4. You edit humanized.txt if you want, then press y
    5. It asks for a typing speed (default 120 WPM)
    6. It types the text like a human — with pauses, typos, corrections,
       and little thinking hesitations.

macOS: typing needs Accessibility permission (System Settings -> Privacy &
Security -> Accessibility) for your terminal. Typing goes to whatever window is
focused when the countdown ends.
"""

import atexit
import json
import os
import random
import re
import socket
import subprocess
import sys
import time
from dataclasses import dataclass

import requests

try:
    from pynput.keyboard import Controller, Key
except ImportError:
    Controller = None
    Key = None

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
HERE           = os.path.dirname(os.path.abspath(__file__))
MESSAGE_FILE   = os.path.join(HERE, "message.txt")
STYLE_FILE     = os.path.join(HERE, "style.txt")
HUMANIZED_FILE = os.path.join(HERE, "humanized.txt")

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Config:
    ssh_user:            str   = "sithoreo"
    ssh_host:            str   = "192.168.4.50"
    ssh_key:             str   = os.path.expanduser("~/.ssh/id_ollama")
    local_port:          int   = 11435
    remote_port:         int   = 11434
    model:               str   = "llama3.1:8b-instruct-q8_0"
    connect_timeout:     float = 1.5
    connect_retries:     int   = 20
    connect_retry_delay: float = 0.5
    request_timeout:     int   = 180
    default_wpm:         int   = 120
    typo_rate:           float = 0.05
    max_false_starts:    int   = 8

CFG = Config()

QWERTY_NEIGHBORS = {
    "q": "wa",    "w": "qeas",  "e": "wrds",  "r": "etdf",  "t": "rygf",
    "y": "tuhg",  "u": "yijh",  "i": "uokj",  "o": "iplk",  "p": "ol",
    "a": "qwsz",  "s": "awedxz","d": "serfcx","f": "drtgvc","g": "ftyhbv",
    "h": "gyujnb","j": "huikmn","k": "jiolm", "l": "kop",   "z": "asx",
    "x": "zsdc",  "c": "xdfv",  "v": "cfgb",  "b": "vghn",  "n": "bhjm",
    "m": "njk",
}

# --------------------------------------------------------------------------- #
# Exceptions
# --------------------------------------------------------------------------- #
class TunnelError(RuntimeError):
    pass

class OllamaError(RuntimeError):
    pass

# --------------------------------------------------------------------------- #
# SSH tunnel
# --------------------------------------------------------------------------- #
def _port_open(host: str, port: int, timeout: float = CFG.connect_timeout) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _spawn_tunnel() -> subprocess.Popen:
    if not os.path.isfile(CFG.ssh_key):
        raise TunnelError(f"SSH key not found: {CFG.ssh_key}")
    print("Connecting to the AI server...")
    return subprocess.Popen(
        [
            "ssh", "-i", CFG.ssh_key, "-N",
            "-o", "BatchMode=yes",
            "-o", "ExitOnForwardFailure=yes",
            "-o", "ServerAliveInterval=30",
            "-o", "StrictHostKeyChecking=accept-new",
            "-L", f"{CFG.local_port}:localhost:{CFG.remote_port}",
            f"{CFG.ssh_user}@{CFG.ssh_host}",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )


def _wait_for_tunnel(proc: subprocess.Popen) -> bool:
    for _ in range(CFG.connect_retries):
        if _port_open("127.0.0.1", CFG.local_port):
            return True
        if proc.poll() is not None:
            stderr = proc.stderr.read().decode().strip() if proc.stderr else ""
            raise TunnelError(
                f"SSH process exited early. Is the server reachable?\n{stderr}"
            )
        time.sleep(CFG.connect_retry_delay)
    return False


def open_tunnel() -> str:
    """Open (or reuse) an SSH tunnel. Returns the Ollama base URL."""
    if _port_open("127.0.0.1", CFG.local_port):
        return f"http://127.0.0.1:{CFG.local_port}"
    proc = _spawn_tunnel()
    if not _wait_for_tunnel(proc):
        proc.terminate()
        raise TunnelError("Timed out waiting for SSH tunnel to become ready.")
    atexit.register(proc.terminate)
    return f"http://127.0.0.1:{CFG.local_port}"

# --------------------------------------------------------------------------- #
# Ollama client
# --------------------------------------------------------------------------- #
class OllamaClient:
    def __init__(self, base_url: str, model: str = CFG.model):
        self.base_url = base_url.rstrip("/")
        self.model    = model
        self._session = requests.Session()

    def generate(self, prompt: str, system: str = "", temperature: float = 0.4) -> str:
        try:
            resp = self._session.post(
                f"{self.base_url}/api/generate",
                json={
                    "model":   self.model,
                    "prompt":  prompt,
                    "system":  system,
                    "stream":  False,
                    "options": {"temperature": temperature},
                },
                timeout=CFG.request_timeout,
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            raise OllamaError(f"Ollama request failed: {e}") from e
        return resp.json().get("response", "").strip()

    def close(self):
        self._session.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

# --------------------------------------------------------------------------- #
# Humanize
# --------------------------------------------------------------------------- #
def humanize(client: OllamaClient, message: str, style: str) -> str:
    system = (
        "You are a light copy-editor. You adjust word choice and phrasing so text "
        "matches a target writing style, while preserving the meaning, facts, and "
        "structure exactly. Output ONLY the edited text: no preamble, no notes, "
        "no surrounding quotes."
    )
    prompt = f"""Lightly rewrite the MESSAGE so its wording and tone match the WRITING STYLE.

RULES:
- Keep all facts, examples, names, and the original meaning. Add/remove nothing.
- Keep the structure: same paragraphs, line breaks, lists, headings, numbers.
- Only change phrasing and word choice for tone. Don't make it flowery.
- The WRITING STYLE shows HOW the person writes, not WHAT to write about.
  Don't borrow topics or phrases from it.
- Output ONLY the rewritten message.

WRITING STYLE (a sample of the person's writing):
\"\"\"
{style[:6000]}
\"\"\"

MESSAGE:
\"\"\"
{message}
\"\"\"
"""
    return strip_preamble(client.generate(prompt, system))


def strip_preamble(text: str) -> str:
    """Drop a leading 'Here's the rewrite:' line and any wrapping quotes."""
    text = text.strip()
    parts = text.split("\n", 1)
    if len(parts) == 2:
        first = parts[0].lower().rstrip()
        if first.endswith(":") and any(
            k in first for k in ("here", "rewrit", "version", "sure", "style")
        ):
            text = parts[1].strip()
    if len(text) >= 2 and text[0] in "\"'" and text[-1] == text[0]:
        text = text[1:-1].strip()
    return text

# --------------------------------------------------------------------------- #
# False starts
# --------------------------------------------------------------------------- #
def to_sentences(text: str) -> list[list[str]]:
    """Split into paragraphs, each a list of sentence strings."""
    paras = []
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if para:
            paras.append(re.split(r"(?<=[.!?])\s+", para))
    return paras


def parse_json(text: str):
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return None


def generate_false_starts(client: OllamaClient, paras: list[list[str]]) -> dict[int, str]:
    """Ask the AI for short alternative sentence openings to 'type then delete'.

    Returns {flat_sentence_index: false_start_text}. Best effort — empty on failure.
    """
    flat = [s for para in paras for s in para]
    candidates = [i for i, s in enumerate(flat) if len(s.split()) >= 7]
    if not candidates:
        return {}
    chosen = sorted(random.sample(candidates, min(CFG.max_false_starts, len(candidates))))
    listing = "\n".join(f"{i}: {flat[i]}" for i in chosen)
    system = (
        "You write realistic 'false starts' — the first few words a writer might type "
        "to begin a sentence, then delete and rephrase. Respond ONLY with JSON."
    )
    prompt = f"""For each numbered SENTENCE, write a SHORT alternative opening (3 to 7 words)
that the writer might start typing first, before changing their mind and writing the
real sentence. It must sound like a natural first attempt at the SAME idea, must NOT
match the real wording, and must NOT be a complete sentence (no ending punctuation).

Return JSON: {{"starts": [{{"id": <number>, "text": "<alternative opening>"}}]}}

SENTENCES:
{listing}
"""
    data = parse_json(client.generate(prompt, system, temperature=0.8))
    out: dict[int, str] = {}
    if data and isinstance(data.get("starts"), list):
        for item in data["starts"]:
            try:
                i = int(item["id"])
                t = str(item["text"]).strip().rstrip(".!?,;: ")
            except (KeyError, ValueError, TypeError):
                continue
            if t and i in chosen and len(t) <= 60:
                out[i] = t
    return out

# --------------------------------------------------------------------------- #
# Human-like typing
# --------------------------------------------------------------------------- #
def maybe_typo(char: str) -> str | None:
    """Return a wrong string to type-then-fix, or None."""
    if not char.isalpha() or random.random() >= CFG.typo_rate:
        return None
    low = char.lower()
    if random.random() < 0.5 and low in QWERTY_NEIGHBORS:
        wrong = random.choice(QWERTY_NEIGHBORS[low])
        return wrong.upper() if char.isupper() else wrong
    return char + char  # doubled letter


def type_like_human(text: str, wpm: int, false_starts: dict | None = None) -> None:
    false_starts = false_starts or {}
    kb   = Controller()
    cps  = (wpm * 5) / 60.0
    base = 1.0 / max(1.0, cps)

    def char_delay(c: str, prev: str) -> float:
        d = base * random.uniform(0.6, 1.5)
        if c in ".,!?;:":
            d += random.uniform(0.15, 0.5)
        if prev in ".!?":
            d += random.uniform(0.2, 0.6)
        return d

    def backspace(n: int) -> None:
        for _ in range(n):
            kb.press(Key.backspace)
            kb.release(Key.backspace)
            time.sleep(random.uniform(0.04, 0.12))

    def type_plain(seg: str) -> None:
        prev = ""
        for char in seg:
            kb.type(char)
            time.sleep(char_delay(char, prev))
            prev = char

    def type_real(seg: str) -> None:
        prev = ""
        for char in seg:
            typo = maybe_typo(char)
            if typo:
                for c in typo:
                    kb.type(c)
                    time.sleep(char_delay(c, prev))
                time.sleep(random.uniform(0.2, 0.8))
                backspace(len(typo))
                kb.type(char)
                time.sleep(char_delay(char, prev))
            else:
                kb.type(char)
                time.sleep(char_delay(char, prev))
            prev = char
            if char == " " and random.random() < 0.08:
                time.sleep(random.uniform(0.5, 2.5))

    idx = 0
    for p_idx, sentences in enumerate(to_sentences(text)):
        if p_idx > 0:
            kb.type("\n\n")
            time.sleep(random.uniform(1.5, 3.5))
        for s_idx, sentence in enumerate(sentences):
            fs = false_starts.get(idx)
            if fs:
                type_plain(fs)
                time.sleep(random.uniform(0.5, 1.3))
                backspace(len(fs))
                time.sleep(random.uniform(0.3, 0.7))
            type_real(sentence)
            if s_idx < len(sentences) - 1:
                kb.type(" ")
            idx += 1

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def die(msg: str) -> None:
    print(f"\nError: {msg}")
    sys.exit(1)


def read_file(path: str, label: str) -> str:
    if not os.path.isfile(path):
        die(f"{label} not found: {path}")
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def countdown(seconds: int = 5) -> None:
    print("\nSwitch to the window you want to type into!")
    for i in range(seconds, 0, -1):
        print(f"  typing in {i}...", end="\r", flush=True)
        time.sleep(1)
    print("  go!            ")

# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> None:
    if Controller is None:
        die("pynput not installed. Run: .venv/bin/pip install -r requirements.txt")

    message = read_file(MESSAGE_FILE, "message.txt").strip()
    if not message:
        die("message.txt is empty. Put your message in it and run again.")
    style = read_file(STYLE_FILE, "style.txt").strip()

    try:
        base_url = open_tunnel()
    except TunnelError as e:
        die(str(e))

    # Always open the client — needed for false starts even without humanizing
    with OllamaClient(base_url) as client:

        # ------------------------------------------------------------------- #
        # Step 1: humanize or use raw message
        # ------------------------------------------------------------------- #
        want_humanize = input("Do you want it humanized? (yes/no): ").strip().lower()

        if want_humanize in ("yes", "y"):
            print("Humanizing your message...")
            try:
                result = humanize(client, message, style)
            except OllamaError as e:
                die(str(e))
        else:
            result = message

        with open(HUMANIZED_FILE, "w", encoding="utf-8") as f:
            f.write(result)

        print(f"\nDone. The text is in:\n  {HUMANIZED_FILE}\n")
        print("Open that file, make any edits you want, and save it.")

        # ------------------------------------------------------------------- #
        # Step 2: review loop — same regardless of humanize choice
        # ------------------------------------------------------------------- #
        while True:
            ans = input("Press y to type it out, r to reload your edits, or q to quit: ").strip().lower()
            if ans == "q":
                print("Okay, nothing typed.")
                return
            if ans in ("y", "r"):
                result = read_file(HUMANIZED_FILE, "humanized.txt").strip()
                if not result:
                    print("humanized.txt is empty — add some text first.")
                    continue
                if ans == "y":
                    break
                print("Reloaded your edits.")

        # ------------------------------------------------------------------- #
        # Step 3: speed + false starts + type
        # ------------------------------------------------------------------- #
        raw = input(f"\nTyping speed in WPM [default {CFG.default_wpm}]: ").strip()
        try:
            wpm = int(raw) if raw else CFG.default_wpm
        except ValueError:
            wpm = CFG.default_wpm
        wpm = max(10, min(400, wpm))

        print("Planning a few natural false starts...")
        try:
            false_starts = generate_false_starts(client, to_sentences(result))
        except (OllamaError, SystemExit):
            false_starts = {}

        countdown(5)
        try:
            type_like_human(result, wpm, false_starts)
        except KeyboardInterrupt:
            print("\nStopped.")
            return

    print("\nDone.")


if __name__ == "__main__":
    main()