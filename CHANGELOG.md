# Changelog

## v1.0.0

First public release of Mini-Claude, a pixel Claude crab desktop pet for Windows.

**Pet**
- Lives above all windows, walks along the taskbar, climbs onto and jumps between windows, falls with simple physics.
- Click to make him jump with hearts, stroke with the mouse to make him purr, drag him around by the claws.
- Moods and hunger: feed him a cookie; a hungry crab walks slower and gets sad.
- Sleeps when idle, dances when music is playing, wears seasonal hats (or pick one: Santa, witch, party, crown, top hat).
- Friends: call colored crabs that wander around and wave at him.
- Reminders (in N minutes or at a time) and a Pomodoro timer (25/5 minutes).
- Tray icon (click to hide/show), "do not disturb for 1 hour", optional autostart with Windows.
- Pixel sounds and optional spoken phrases (Windows SAPI voice).

**Claude Code integration (optional)**
- Ask about the active window (with a screenshot): double click or Ctrl+Alt+C.
- Selected text actions with Ctrl+Alt+T: translate, fix mistakes, make it more polite/shorter, explain; result can be pasted back automatically.
- Ask about a screen area: Ctrl+Alt+S. Ask by voice: Ctrl+Alt+V.
- Reacts to Claude Code via a hook: thinks while Claude works, cheers when done, alerts when it needs you.
- Windows with words like "bank" or "password" in the title are never sent anywhere.

**Customization**
- Edit `animations.py` to redraw sprites, add animations, phrases and hats; reload from Settings without restarting.
- Settings are stored in `%USERPROFILE%\.claude-pet\settings.json`.

**Release asset:** `ClaudePet.exe` (single-file Windows build, no Python required; unsigned, so Windows SmartScreen may warn).

> Unofficial fan project, not affiliated with or endorsed by Anthropic. Claude is a trademark of Anthropic.
