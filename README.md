# MadCowork Module Contract

Build a module for the [MadCowork flagship app](https://github.com/MadCowork/MadCowork).
Ship it as one file so users can install it without a terminal, a Python install,
or your help.

This repository is the **module-authoring contract and reference profile**. It
does not define MadCowork's product architecture, agent loop, workspace model,
or remote-compute control plane. MadCowork owns those systems; a module adds a
bounded capability to them through MCP, an optional skill, and a local screen.
Do not build a second agent platform merely because the extension transport is
MCP.

Use these product documents with this contract:

| Document | Authority |
|---|---|
| [Architecture](https://github.com/MadCowork/MadCowork/blob/develop/MadCowork-api/docs/madcowork-architecture-zh.md) | How MadCowork sessions, tools, workspaces, permissions, and runtimes fit together |
| [Plugin development](https://github.com/MadCowork/MadCowork/blob/develop/MadCowork-api/docs/plugin-development.md) | What the current host actually installs and consumes |
| [Sandbox and confinement](https://github.com/MadCowork/MadCowork/blob/develop/MadCowork-api/docs/sandbox-and-confinement.md) | Product command/hook confinement design; this contract records the current plugin-runtime boundary separately |
| [Audited 0.61.0 host baseline](https://github.com/MadCowork/MadCowork/tree/204a64a83f2600711b37b412f626c8474c63fa5b/MadCowork-api) | Immutable compatibility reference used for the truth table below |

A module can provide tools the model calls, a screen the person operates, and
instructions that teach the model when to use those tools. A trusted local
stdio module runs as a separate process **with the permissions of the signed-in
OS user**. Process separation is a failure boundary; it is not a security
sandbox.

```
your-module/
  plugin.json      identity and compatibility
  mcp.json         how your server starts
  server.py        your tools
  ui/index.html    your screen              (required by this reference profile)
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

The checker regression suite includes mutated panel consumers that must warn or
fail for the intended reason:

```sh
python3 -m unittest discover -s tests -v
```

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

## Trust is consent, not a sandbox

| State or boundary | What is true today |
|---|---|
| Installed but untrusted | Plugin MCP servers, hooks, and skills are withheld; local plugin code does not start |
| Trusted local stdio module | Its process runs as the signed-in OS user and can access user-readable files and the network |
| Environment filtering | Provider key values and the host vault key are not copied into the child environment, but `HOME`, workspace/data paths, and `MADCOWORK_ENV_PATH` may be present; filtering is **not** filesystem confinement |
| Tool approval | Plugin MCP tools are marked unsafe and go through MadCowork's action policy; an allow-all or always-allow choice may skip repeated prompts |
| Remote MCP server | It runs in its own remote security boundary; this package contract does not define that infrastructure |

Only install and Trust code you would be willing to run under your own account.
A trusted local module may read or modify anything that account can reach,
including MadCowork configuration files. It must never modify MadCowork's app,
signature, registry, or credentials, but that is an author obligation—not an OS
sandbox guarantee.

### What enforces each rule

| Enforcement layer | Enforced now |
|---|---|
| MadCowork host | Install starts untrusted; trust gates MCP/hooks/skills; `minimumHostVersion` is checked when present; wrapped tool collisions are blocked; tool calls enter the host action policy |
| This repository's checker | Full reference-profile manifest, UI/CSP, sentinel, entry-point, invariant, panel, i18n, and Known Limitations rules |
| Convention / future host | Native use of `moduleApiVersion` and `entryPoints`, `ui://`, and a bundled `madcowork plugin check` command |

The host currently accepts a smaller manifest than this reference profile. Run
the checker in CI: fields required here are not automatically revalidated by
the installed app unless the table explicitly says the host enforces them.

## Documents

| | |
|---|---|
| [spec/contract-v1.md](spec/contract-v1.md) | The full contract |
| [tools/check_contract.py](tools/check_contract.py) | The checker |
| [template/](template/) | A minimal module that already passes the checker |

## Versioning

The contract is versioned. `plugin.json` declares `moduleApiVersion` (the
contract you built against — required by the checker) and `minimumHostVersion`
(the oldest MadCowork that can run you — enforced by the host, which refuses to
install a module that needs a newer host than it is). The host does not yet act
on `moduleApiVersion`; it exists so the checker, and future hosts, can detect
contract drift instead of failing mysteriously on a user's machine.

## License

Apache-2.0. The contract, the checker and the template are yours to use.
