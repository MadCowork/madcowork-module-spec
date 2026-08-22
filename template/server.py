"""A minimal MadCowork module: one tool, one screen, one skill.

Copy this directory, rename it, and start replacing. It already passes
`tools/check_contract.py`, so the first red line you see will be about
your change — not about the skeleton.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from _local_ui import LocalUiServer
from _panel import PanelChannel
from _mcp_runtime import McpServer

MAD_HOME = Path(__file__).resolve().parents[2]
DATA_DIR = MAD_HOME / "module-data" / "example-module"
DB_PATH = DATA_DIR / "notes.sqlite3"
SCHEMA_VERSION = 1
VERSION = "0.1.0"


def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(
        "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);"
        "CREATE TABLE IF NOT EXISTS notes ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " body TEXT NOT NULL,"
        " created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);"
    )
    conn.execute("INSERT OR IGNORE INTO meta(key,value) VALUES('schema_version',?)",
                 (str(SCHEMA_VERSION),))
    conn.commit()
    return conn


def tool_doctor(args: dict) -> dict:
    with _connect() as conn:
        count = conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
    return {"version": VERSION, "schema_version": SCHEMA_VERSION,
            "data_dir": str(DATA_DIR), "notes": count,
            "note": "This module stores notes locally. It sends nothing anywhere."}


def tool_add_note(args: dict) -> dict:
    body = str(args.get("body") or "").strip()
    if not body:
        raise ValueError("body is required")
    with _connect() as conn:
        cur = conn.execute("INSERT INTO notes(body) VALUES(?)", (body,))
        conn.commit()
    return {"note_id": cur.lastrowid, "body": body}


def tool_list_notes(args: dict) -> dict:
    with _connect() as conn:
        rows = conn.execute("SELECT id, body, created_at FROM notes ORDER BY id DESC").fetchall()
    return {"notes": [dict(r) for r in rows]}


# The panel channel makes this module agent-driven rather than a dashboard:
# the model can point the screen somewhere, write a card on it, and ask what
# the user is looking at. `pull` and `dismiss` belong to the page, never to
# the model — keep them out of TOOLS.
PANEL = PanelChannel(tabs=("notes", "about"))

UI = LocalUiServer("example-module", Path(__file__).resolve().parent / "ui", {
    "list_notes": tool_list_notes,
    "add_note": tool_add_note,
    "panel_pull": PANEL.pull,
    "panel_dismiss": PANEL.dismiss,
})


def tool_open_ui(args: dict) -> dict:
    return UI.open()


TOOLS = [
    {"name": "example_doctor",
     "description": "Report module version, schema version and where data lives.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "example_add_note",
     "description": "Store one note locally.",
     "inputSchema": {"type": "object", "properties": {"body": {"type": "string"}},
                     "required": ["body"]}},
    {"name": "example_list_notes",
     "description": "List every stored note, newest first.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "example_panel_focus",
     "description": "Point the open panel at one of its tabs, so the user sees what you are talking about.",
     "inputSchema": {"type": "object", "properties": {"tab": {"type": "string", "enum": ["notes", "about"]}}}},
    {"name": "example_panel_note",
     "description": "Put a card at the top of the panel with your reading of what is there. Shown labelled as written by the model.",
     "inputSchema": {"type": "object",
                     "properties": {"title": {"type": "string"},
                                    "lines": {"type": "array", "items": {"type": "string"}},
                                    "level": {"type": "string", "enum": ["info", "warn", "danger", "ok"]}},
                     "required": ["title"]}},
    {"name": "example_panel_state",
     "description": "See what the panel is showing right now, and whether it is open at all.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "example_open_ui",
     "description": "Open the notes workbench in MadCowork's browser panel.",
     "inputSchema": {"type": "object", "properties": {}}},
]

HANDLERS = {
    "example_doctor": tool_doctor,
    "example_add_note": tool_add_note,
    "example_list_notes": tool_list_notes,
    "example_panel_focus": PANEL.focus,
    "example_panel_note": PANEL.note,
    "example_panel_state": PANEL.state,
    "example_open_ui": tool_open_ui,
}

# What the model may call: exactly what it can see. HANDLERS also carries
# the page's own entry points, so dispatching on it would make "not in
# tools/list" a convention with nothing enforcing it — see §11b.
MODEL_TOOLS = {entry["name"] for entry in TOOLS}
_orphans = MODEL_TOOLS - set(HANDLERS)
assert not _orphans, f"declared tools with no handler: {sorted(_orphans)}"


def handle(name: str, args: dict):
    if name not in MODEL_TOOLS:
        raise ValueError(f"unknown tool: {name}")
    return HANDLERS[name](args or {})


if __name__ == "__main__":
    McpServer("example-module", VERSION, TOOLS, handle).run()
