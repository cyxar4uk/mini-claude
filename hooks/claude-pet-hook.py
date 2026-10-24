# Хук Claude Code для Клода-питомца: записывает, чем сейчас занят Claude,
# в ~/.claude/pet-state.json. Ничего не печатает и никогда не падает,
# чтобы не мешать работе Claude Code.
import json
import os
import sys
import time

if os.environ.get("CLAUDE_PET_INTERNAL"):  # это сам питомец спрашивает Claude
    sys.exit(0)

try:
    state = sys.argv[1] if len(sys.argv) > 1 else "idle"
    try:
        data = json.load(sys.stdin)
    except Exception:
        data = {}
    out = {
        "state": state,
        "message": data.get("message", "") if state == "attention" else "",
        "session": data.get("session_id", ""),
        "t": time.time(),
    }
    path = os.path.join(os.path.expanduser("~"), ".claude", "pet-state.json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    os.replace(tmp, path)
except Exception:
    pass
