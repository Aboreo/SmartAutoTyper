# Smart Auto Typer

Types a message for you, in your own writing style, like a human would — with
realistic speed, pauses, and the occasional typo it fixes. **No flags, no options.**

## How to use it

1. Put the message you want to send in **`message.txt`**.
2. Run it:
   ```bash
   aiat
   ```
   (or `.venv/bin/python ollama_typer.py`)
3. It rewrites your message in your style and saves it to **`humanized.txt`**.
4. Open `humanized.txt`, make any edits you want, save it.
5. Back in the terminal, press **`y`** to type it (`r` to reload your edits, `q` to quit).
6. It asks for a typing speed — press Enter for the default **120 WPM**, or type a number.
7. A 5-second countdown starts — click into the window you want it typed into.
8. It types. Press **Ctrl+C** anytime to stop.

## The files (all in this folder)

| File | What it's for |
|---|---|
| `message.txt` | The message you want to type. **You edit this.** |
| `style.txt` | Examples of how *you* write, so it can match your voice. Set once. |
| `humanized.txt` | The rewritten version. Auto-created; edit before pressing `y`. |

## One-time setup

- **Style sample:** put a few examples of your real writing in `style.txt`.
- **Permission (for typing):** System Settings → Privacy & Security → Accessibility →
  enable your terminal app. Without it, macOS silently blocks the typing.
- **AI server:** the rewriting runs on the Ubuntu box (`192.168.4.50`). Just make sure
  it's on and on the network — the program connects to it automatically (no password).

That's it.
