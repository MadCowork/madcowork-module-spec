---
name: example-notes
description: |
  Store and read short notes with the example module. Everything stays on this
  machine; nothing is sent anywhere.
  Triggers: take a note / jot this down / save a note / what notes do I have /
  記一下 / 存成筆記 / 我有哪些筆記
---

# Notes (example-module)

## When to use this

The person wants to write something down, or asks what they have written before.

## Tool names

The tools appear in your list with an MCP prefix — **not** the bare names:

| To do this | Call |
|---|---|
| Store a note | `mcp__example-module-server__example_add_note` |
| List every note | `mcp__example-module-server__example_list_notes` |
| Open the notes screen | `mcp__example-module-server__example_open_ui` |
| Check the module | `mcp__example-module-server__example_doctor` |

> The prefix comes from the server name in `mcp.json`. If you cannot find these
> names in your tool list, the module is not trusted or not loaded — **do not
> fall back to the bare name, it will not work**. Tell the person to check
> Settings → Plugins.

## What this module does not do

It does not sync, publish, or send anything. Notes live in
`~/.madcowork/module-data/example-module/`. Do not tell the person their note
was shared or backed up anywhere.
