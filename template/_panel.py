"""The panel channel — what makes a module agent-driven instead of a dashboard.

A module with tools but no channel is two pipes that never meet: the model
reads data and can open your screen, but cannot see what is on it or change
it, and the person looking at the screen cannot hand anything back. This
class is the meeting point, and it is deliberately small:

    channel = PanelChannel(tabs=("overview", "settings"))

    # model-facing (put these in TOOLS)
    channel.focus({"tab": "settings"})        # point the panel somewhere
    channel.note({"title": ..., "lines": [...], "level": "warn"})
    channel.state({})                         # what is the user looking at?

    # panel-facing (keep these OUT of TOOLS)
    channel.pull({"state": {...}})            # the page polls this
    channel.dismiss({})

Three rules are baked in rather than left to each author:

* A card says who wrote it. Model prose sitting unmarked beside measured
  numbers is the worst thing this feature can do, so `note()` records the
  author and the UI is expected to label it.
* Focus is a one-shot instruction. Replayed on every poll it would fight the
  user for the tab they just chose.
* Nothing here touches your backend, your cluster or the network. The poll is
  loopback and cheap on purpose; a channel that costs a remote call per tick
  would be a channel people turn off.

State lives in memory only: a panel instruction is about right now, and
outliving the process would make it a lie.
"""

from __future__ import annotations

import threading
import time

MAX_CARDS = 5
MAX_CARD_LINES = 12
LEVELS = ("info", "warn", "danger", "ok")


class PanelChannel:
    def __init__(self, tabs=(), author="MadCowork", max_cards=MAX_CARDS):
        self.tabs = tuple(tabs)
        self.author = author
        self.max_cards = max_cards
        self._lock = threading.Lock()
        self._seq = 0
        self._focus: dict = {}
        self._cards: list[dict] = []
        self._state: dict = {}

    # ── model-facing ──────────────────────────────────────────────────
    def focus(self, args: dict) -> dict:
        wanted = {}
        tab = str(args.get("tab") or "").strip().lower()
        if tab:
            if self.tabs and tab not in self.tabs:
                raise ValueError(f"tab must be one of {list(self.tabs)}")
            wanted["tab"] = tab
        for key, value in (args.get("extra") or {}).items():
            wanted[str(key)[:32]] = str(value)[:120]
        if not wanted:
            raise ValueError("nothing to focus: give a tab (or extra values)")
        with self._lock:
            self._seq += 1
            self._focus = wanted
            return {"ok": True, "seq": self._seq, **wanted}

    def note(self, args: dict) -> dict:
        title = str(args.get("title") or "").strip()
        if not title:
            raise ValueError("title is required")
        lines = args.get("lines")
        if isinstance(lines, str):
            lines = [lines]
        lines = [str(line).strip() for line in (lines or []) if str(line or "").strip()]
        level = str(args.get("level") or "info").strip().lower()
        if level not in LEVELS:
            raise ValueError(f"level must be one of {list(LEVELS)}")
        card = {"title": title[:120], "lines": lines[:MAX_CARD_LINES],
                "level": level, "author": self.author, "at": int(time.time())}
        with self._lock:
            self._seq += 1
            self._cards = (self._cards + [card])[-self.max_cards:]
            return {"ok": True, "seq": self._seq, "cards": len(self._cards)}

    def state(self, _args: dict = None) -> dict:
        with self._lock:
            state = dict(self._state)
            cards = len(self._cards)
        if not state:
            return {"open": False, "note": "the panel has not reported in — it may not be open"}
        return {"open": time.time() - float(state.get("at") or 0) < 20, "cards": cards, **state}

    # ── panel-facing (never expose these to the model) ────────────────
    def pull(self, args: dict) -> dict:
        report = (args or {}).get("state")
        with self._lock:
            if isinstance(report, dict):
                self._state = {str(k)[:32]: str(v)[:200] for k, v in report.items()}
                self._state["at"] = time.time()
            payload = {"seq": self._seq, "focus": dict(self._focus), "cards": list(self._cards)}
            self._focus = {}
        return payload

    def dismiss(self, _args: dict = None) -> dict:
        with self._lock:
            self._cards = []
            self._seq += 1
        return {"ok": True}
