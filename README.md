# MadCowork Module Contract

Build a module for [MadCowork](https://github.com/MadCowork). Ship it as one file.
Users install it without a terminal, a Python install, or your help.

A module gives MadCowork new abilities — tools the model can call, a screen the
person can operate, and instructions that teach the model when to use them. It
runs as a separate process, holds no credentials, and cannot break the host: if
your module fails to load, MadCowork still starts.

```
your-module/
  plugin.json      identity and compatibility
  mcp.json         how your server starts
  server.py        your tools
  ui/index.html    your screen              (required, not optional)
  skills/          teach the model when to use you
  invariant.py     how your module knows its own data is broken
  README.md        including "Known Limitations"
```

```sh
madcowork plugin pack your-module/      # → your-module.mcpkg (in your current directory)
```

That single `.mcpkg` is the whole delivery.

> **Only have the packaged app?** There is no `madcowork` on your PATH yet — the
> CLI lives inside the app bundle. Use the full path (adjust the app name to
> what is in your `/Applications`):
>
> ```sh
> ELECTRON_RUN_AS_NODE=1 \
>   "/Applications/MadCowork.app/Contents/MacOS/madcowork-api" \
>   "/Applications/MadCowork.app/Contents/Resources/app/server/cli.mjs" \
>   plugin pack your-module/
> ```

## Check your module before anyone installs it

```sh
python3 tools/check_contract.py path/to/your-module
```

> No Python on your machine? MadCowork bundles one — use it directly:
>
> ```sh
> "/Applications/MadCowork.app/Contents/Resources/runtime/python/bin/python3.11" \
>   tools/check_contract.py path/to/your-module
> ```

The checker enforces what this contract requires, and it is the same one the
reference module runs in its own CI. **Run it yourself — do not wait for a user
to install the package and discover the problem.**

It catches, among others:

| Rule | Why it exists |
|---|---|
| CSS and JS must be external files | The UI is served under `style-src 'self'`. Inline styles are **silently refused** — HTTP 200, correct byte count, your JS still runs, and the screen renders bare. Byte-level tests cannot see this. |
| Skills must name tools the way the model sees them | The model sees `mcp__<server>__<tool>`, not your bare tool name. A skill that names the bare tool sends the model looking for something that does not exist, with no error. |
| Every module declares a runtime invariant, or says why it has none | A module that cannot detect its own corrupted data will report healthy while serving wrong answers. |
| Every module states its Known Limitations | An optimistic silence reads downstream as a guarantee. |

**The checker never guesses.** When it cannot read your tool declarations it says
so plainly instead of accusing you of shipping tools that do not exist.

## The three rules that catch people out

**1. Your UI runs under a strict Content-Security-Policy.** Put CSS and JS in
separate files. Inline `<style>`, `style="…"`, inline `<script>` and `on…=`
handlers are all refused, and the failure is invisible from the server side.

**2. The model does not see your tool names.** It sees them prefixed:

```
you declare        mail_create_draft
the model sees     mcp__your-module-server__mail_create_draft
```

Write the prefixed name in your skill, or describe the capability without naming
tools at all.

**3. Never write absolute paths.** Use the `madcowork:python` sentinel in
`mcp.json` so your module runs on a machine that has no Python of its own. Store
data under `~/.madcowork/module-data/<your-name>/`, never inside your module
directory — that directory disappears when the module is removed.

## What a module cannot do

| | |
|---|---|
| ❌ Touch MadCowork itself or its signature | Your module lives outside the app |
| ❌ Read the user's credentials | The stdio environment is an allowlist; the vault key is not in it |
| ❌ Run on install | Installed means `enabled + untrusted`. Nothing of yours executes until a person presses Trust |

These are not restrictions we expect you to respect voluntarily. **The host
enforces them.** Where this contract says "must", the host rejects packages that
do not — it does not rely on authors being careful.

## Documents

| | |
|---|---|
| [spec/contract-v1.md](spec/contract-v1.md) | The full contract |
| [tools/check_contract.py](tools/check_contract.py) | The checker |
| [template/](template/) | A minimal module that already passes the checker |

## Versioning

The contract is versioned. `plugin.json` declares `moduleApiVersion` (what
contract you built against) and `minimumHostVersion` (the oldest MadCowork that
can run you). The host reads both and refuses installs it cannot honour, so a
user never ends up with a module that fails mysteriously on their machine.

## License

Apache-2.0. The contract, the checker and the template are yours to use.
