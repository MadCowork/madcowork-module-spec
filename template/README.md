# example-module

A minimal MadCowork module: one screen, four tools, one skill. It stores short
notes locally and sends nothing anywhere.

Copy this directory, rename it, and start replacing. **It already passes
`check_contract.py`**, so the first failure you see will be about your change —
not about the skeleton.

```sh
python3 ../tools/check_contract.py .     # 0 FAIL / 0 WARN
madcowork plugin pack .                  # → example-module-0.1.0-universal.mcpkg
```

## What to change first

| File | What it is for |
|---|---|
| `plugin.json` | Your name, version, and `repository` — replace all three |
| `mcp.json` | Server name; it becomes the prefix the model sees |
| `server.py` | Your tools |
| `ui/` | Your screen. **CSS stays in `style.css`** — inline styles are refused by CSP |
| `skills/` | When the model should use you. **Tool names must carry the MCP prefix** |
| `invariant.py` | How your module notices its own data is broken |

## Known Limitations

- **Notes are plain text, stored unencrypted** in a local SQLite file. Anyone
  with read access to the user's home directory can read them.
- **No search, no tags, no edit or delete.** This is a skeleton meant to be
  replaced, not a finished notes app.
- **No migration path.** The schema is version 1 and there is no upgrade or
  versioned backup, so a future schema change would need one added first.
