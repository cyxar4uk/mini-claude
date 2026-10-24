# Mini-Claude

**English** | [Русский](README.ru.md)

A pixel Claude crab desktop pet for Windows. He lives above all windows, walks along the taskbar and on top of your windows, sits in the tray, makes little sounds, and can optionally help you through [Claude Code](https://docs.claude.com/en/docs/claude-code).

<!-- TODO: add a real recording at docs/demo.gif and uncomment:
![Demo](docs/demo.gif)
-->

![Sprite frames: idle, walk, happy, purr, sleep, wave, dance, think, eat, sad](docs/sprites.png)

*Sprite frames rendered straight from `animations.py`.*

> **Unofficial fan project.** Not affiliated with, endorsed by, or sponsored by Anthropic. "Claude" is a trademark of Anthropic. The UI language of the app is currently Russian.

## Features

- Always on top; walks on the taskbar, climbs and jumps between windows, falls when dropped (simple physics).
- Reacts to the mouse: click to jump with hearts, wiggle the cursor over him to make him purr, drag him around.
- Mood and hunger: feed him a cookie; a hungry crab is slower and sad.
- Sleeps when idle, dances when music plays, wears seasonal hats (or choose Santa / witch / party / crown / top hat).
- "Friends": colored crabs that wander around and wave at him.
- Reminders (in N minutes or at a given time) and a Pomodoro timer (25 min work / 5 min break).
- Tray icon (click toggles visibility), "do not disturb for 1 hour", optional autostart with Windows.
- Pixel sound effects, optional spoken phrases (Windows SAPI voice).
- Fully hackable: sprites, animations, phrases and hats live in `animations.py`.

### Optional: Claude Code helper features

These need [Claude Code](https://docs.claude.com/en/docs/claude-code) installed and logged in (run `claude`, then `/login`). The pet calls `claude -p` in an empty temp folder, without your settings or hooks, with only the `Read` tool (to look at the screenshot), so it cannot change anything on your computer.

- Ask about the active window, with a screenshot.
- Selected-text actions: translate, fix mistakes, make more polite / shorter, explain; the result can be pasted over the selection automatically.
- Ask about a region of the screen; ask by voice (Windows voice typing).
- Reacts to what Claude Code is doing (thinks while it works, cheers when done, alerts when it needs you) via a small hook, see [below](#claude-code-hook).
- Windows whose title contains words like "bank" or "password" are never sent anywhere.

## Controls

| Action | Result |
| --- | --- |
| Click | jumps with hearts |
| Wiggle the mouse over him | purrs (mood goes up) |
| Drag | dangles his legs; drop him and he falls, maybe onto a window |
| Double click or **Ctrl+Alt+C** | "how can I help?" box for the active window (with screenshot) |
| **Ctrl+Alt+T** on selected text | translate / fix / politer / shorter / explain |
| **Ctrl+Alt+S** | draw a region on screen and ask about it |
| **Ctrl+Alt+V** | ask by voice |
| Right click | menu: reminders, Pomodoro, cookie, animations, friends, settings, hide, quit |

Quit: the X shown on hover, right click then "Close", the tray icon, or `stop-pet.bat`.

## Settings

Right click, then "Settings" (toggles): wander on his own, climb on windows, dance to music, talk (speech bubbles), speak aloud, sounds, react to Claude Code, tips for the active window, paste processed text over the selection, always on top, start with Windows, hat, reload animations. Settings, mood and reminders are saved to `%USERPROFILE%\.claude-pet\settings.json` (generated sounds and the tray icon are stored there too).

## Run

**Prebuilt exe:** download `ClaudePet.exe` from the [Releases](../../releases) page and run it. No Python needed. The exe is unsigned, so Windows SmartScreen may show a warning.

**From source:**

```bat
git clone https://github.com/cyxar4uk/mini-claude.git
cd mini-claude
pip install -r requirements.txt
start-pet.bat
```

`start-pet.bat` runs `pythonw pet.pyw` (no console window). `stop-pet.bat` closes it.

Requirements: Windows 10/11, Python 3.10+ (developed on 3.12) with tkinter, Pillow; pywin32 optional (spoken phrases).

## Claude Code hook

To let the pet react to Claude Code, copy `hooks/claude-pet-hook.py` somewhere (for example `~/.claude/hooks/`) and register it in `~/.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse":   [{"matcher": "*", "hooks": [{"type": "command", "command": "python \"C:/path/to/claude-pet-hook.py\" working", "timeout": 5}]}],
    "PostToolUse":  [{"matcher": "*", "hooks": [{"type": "command", "command": "python \"C:/path/to/claude-pet-hook.py\" working", "timeout": 5}]}],
    "Stop":         [{"hooks": [{"type": "command", "command": "python \"C:/path/to/claude-pet-hook.py\" done", "timeout": 5}]}],
    "Notification": [{"hooks": [{"type": "command", "command": "python \"C:/path/to/claude-pet-hook.py\" attention", "timeout": 5}]}]
  }
}
```

The hook only writes the current state to `~/.claude/pet-state.json`, which the pet watches.

## Customizing

Edit `animations.py` (next to `pet.pyw`, or next to `ClaudePet.exe`) and choose Settings, "Reload animations" in the menu.

## Building the exe

```bat
pip install -r requirements.txt pyinstaller
build.bat
```

This runs `python -m PyInstaller --onefile --windowed --name ClaudePet --icon icon.ico pet.pyw` and copies `animations.py` into `dist\` so the exe can load your edits. Output: `dist\ClaudePet.exe`.

## Project structure

| File | Purpose |
| --- | --- |
| `pet.pyw` | entry point: main loop, menu, hotkeys, reminders, Pomodoro, Claude Code state |
| `critter.py` | the crab: drawing, physics, mouse handling |
| `animations.py` | palette, pixel frames, animations, phrases, hats |
| `ui.py` | speech bubble, help panel, reminder dialog, screen region selector |
| `helper.py` | questions to Claude via the CLI, screenshots, text actions |
| `winsys.py` | Windows API: windows, global hotkeys, clipboard/keys |
| `sounds.py` | generated sound effects and SAPI voice |
| `tray.py` | tray icon |
| `settings.py` | persistent settings |
| `hooks/claude-pet-hook.py` | optional Claude Code hook |
| `start-pet.bat`, `stop-pet.bat`, `build.bat` | launch, stop, build |

## License

[MIT](LICENSE) (c) 2026 Ilia Melnikov ([@cyxar4uk](https://github.com/cyxar4uk))
