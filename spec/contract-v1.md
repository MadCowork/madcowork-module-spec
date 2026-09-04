# MadCowork Module Contract v1

## 0. In one sentence

**A module is a single `.mcpkg` file. Installed into MadCowork it provides MCP
tools and its own HTML screen; after the user Trusts a local stdio module, its
server runs as that OS user, so Trust is consent to execute code—not a
sandbox.**

### 0.1 Scope and authority

This document is a **module-authoring contract and reference profile**. It does
not define MadCowork's product architecture, agent loop, workspace lifecycle,
or remote-compute control plane. Those belong to the
[flagship architecture](https://github.com/MadCowork/MadCowork/blob/develop/MadCowork-api/docs/madcowork-architecture-zh.md)
and [plugin development](https://github.com/MadCowork/MadCowork/blob/develop/MadCowork-api/docs/plugin-development.md)
documents. Security boundaries are defined in
[sandbox and confinement](https://github.com/MadCowork/MadCowork/blob/develop/MadCowork-api/docs/sandbox-and-confinement.md).
The immutable host baseline used to audit this v1 text is
[MadCowork 0.61.0 at `204a64a`](https://github.com/MadCowork/MadCowork/tree/204a64a83f2600711b37b412f626c8474c63fa5b/MadCowork-api).

MadCowork owns sessions, workspaces, permissions, the model/tool loop, tasks,
and artifacts. A module supplies a capability inside that host. MCP is the
extension transport; its presence is not a reason to build a second agent
platform or duplicate the host control plane.

## 1. What you can and cannot do

| | |
|---|---|
| ✅ Provide MCP tools the model can call | |
| ✅ Provide an HTML screen the person operates | **Required by this reference profile** — see §4 |
| ✅ Store data in `~/.madcowork/module-data/<your-name>/` | Removing the module does not delete it |
| ⚠️ Run with the user's filesystem and network access after Trust | A separate process is a crash boundary, not a security sandbox |
| ❌ Modify MadCowork itself, its signature, registry, or credentials | This is an author obligation; the current local runtime does not OS-sandbox the process |
| ❌ Run anything on install | Installed means `enabled + untrusted`; a person must press Trust |

The child environment is filtered: provider key values and the host vault key
are not copied into it. However, variables such as `HOME`, workspace/data paths,
and `MADCOWORK_ENV_PATH` may be present. A trusted process can also open files
that its OS account can read. **Environment filtering is not filesystem
confinement and is not a credential-access guarantee.**

Plugin MCP tools are marked unsafe and enter MadCowork's action policy. A user
can choose allow-all or always-allow, so this approval layer is not a sandbox
either. Only install and Trust code you would willingly run under your own
account.

A malformed or crashed module should not prevent the host from starting, but
code that has already been Trusted can still damage user-accessible data or
make network requests. Do not describe process isolation as "cannot break the
host."

## 2. What goes in the package

```
your-module/
  plugin.json      identity and compatibility (§3)
  mcp.json         how your server starts (§5)
  server.py        your tools
  ui/index.html    your screen (§4)
  skills/          when the model should use you (§2.1)
  invariant.py     how the module detects its own broken data (§10)
  README.md  CHANGELOG.md  LICENSE
```

Pack it into one file:

```sh
madcowork plugin pack your-module/    # → <name>.mcpkg in the current directory
# Publish it as <name>-<version>.mcpkg so users can tell versions apart.
```

### 2.1 Skills are allowed, and they must name tools the way the model sees them

The host guarantees that **only a trusted plugin's skills reach the model**.
Installing does not expose them; pressing Trust does.

> This rule used to read "the package must not contain `skills/`", because the
> host filtered on *enabled* rather than *trusted*. That ban was a workaround,
> not a fix — and its cost was that **without a skill, the model does not
> naturally use your tools**. A tool appearing in a list is not the same as the
> model knowing when to reach for it. The host now filters on trust, so the ban
> is lifted.

**Get one thing right or the skill is worthless:** the model does not see your
bare tool name. It sees `mcp__<sanitised server name, 24 chars>__<tool name>`.

```
you declare in server.py    mail_create_draft
the model actually sees     mcp__madcowork-mail-module__mail_create_draft
```

**A skill that names only the bare tool sends the model looking for something
that does not exist.** Two acceptable styles:

1. Write the full prefixed name — precise, but breaks if you rename the server.
2. Describe the capability and note that your tools share a prefix — survives renames.

**Add a test of your own** asserting that every tool name mentioned in your
skill exists in the host's wrapped tool list. Otherwise renaming a server or a
tool makes the skill fail silently — and silent failure here looks exactly like
"the model ignores my module", which is hard to diagnose.

## 3. `plugin.json`

```json
{
  "name": "your-module",
  "version": "0.1.0",
  "description": "One line",
  "moduleApiVersion": 1,
  "minimumHostVersion": "0.55.0",
  "repository": "https://github.com/you/your-module",
  "runtimeInvariant": { "module": "invariant", "entry": "check" },
  "entryPoints": {
    "ui":    { "open": "yours_open_ui" },
    "panel": { "focus": "yours_panel_focus",
               "note":  "yours_panel_note",
               "state": "yours_panel_state" }
  }
}
```

| Field | Rule | Enforced today by |
|---|---|---|
| `name` | Globally unique; **also part of your tool-name prefix** — see §6 | Host requires it; checker applies the full profile |
| `version` | SemVer. PATCH = bug fix; MINOR = new backward-compatible tools or fields; MAJOR = removing a tool, changing a required parameter, or breaking a data format | Checker; the 0.61.0 installer does not require it |
| `moduleApiVersion` | Currently `1` | Checker; reserved for a future host contract gate |
| `minimumHostVersion` | **The oldest MadCowork you work on.** When present, the host refuses installs below it | Host and checker |
| `repository` | Where your source lives, so a user can get it | Checker |
| `runtimeInvariant` | See §10 | Checker imports and executes it; the host does not |
| `entryPoints` | Declare entry points explicitly; see the current-host compatibility rule in §3b | Checker; reserved for future native host consumption |

### 3b. `entryPoints` — say what you offer, by name

Optional to the current host, and worth writing. Each entry names a tool of
yours so the checker—and a future host—can read a fact instead of inferring
one. MadCowork 0.61.0 does **not** consume `entryPoints`; its plugin capability
report only describes the package components it found: skills, hooks, and MCP.
It is called `entryPoints` precisely so those two concepts do not share a name.

| Key | Meaning |
|---|---|
| `ui.open` | The tool that opens your screen. **For the current host its name must end in `_open_ui`**, because 0.61.0 discovers loopback screens by that suffix, not by reading this field |
| `panel.focus` / `panel.note` / `panel.state` | Your panel channel (§11b) |

Every name here must appear in `tools/list`; the checker fails you if it does
not, because a declaration that does not resolve is worse than no declaration.

Why this exists: explicit metadata is the intended durable interface. Until the
host consumes it, the checker verifies both the explicit declaration and the
legacy `_open_ui` discovery convention. Panel entries are checker metadata
today; they prevent the checker from guessing channel names.

## 4. The reference profile requires a screen

The 0.61.0 host accepts headless MCP plugins. This reference profile is stricter:
**a module that only offers MCP tools is not complete for this contract**,
because the capability is locked inside the conversation, where nobody but the
model can reach it. The checker—not the current installer—enforces this rule.

**How it is delivered today (v1, transitional):** your module runs a minimal
HTTP server bound to `127.0.0.1` only, and exposes a tool whose name ends in
`_open_ui`. Its successful tool result must be a JSON object with a string
`url`, for example `{"ok": true, "url": "http://127.0.0.1:1234/?token=…"}`.
MadCowork 0.61.0 requires an `http` or `https` URL whose host is `127.0.0.1`,
`localhost`, or `[::1]`; a bare URL string is ignored. It discovers the tool by
the suffix and opens the URL in its browser panel; it does not yet read
`entryPoints.ui.open`.

- **Write endpoints must require a token.** Generate it at start-up with
  `secrets.token_urlsafe()` and verify it from a header (the reference
  implementation uses `X-MadCowork-Module-Token`). **A POST without the token
  must return 403.**
- The token is delivered in the URL query when the tool returns it; your
  front-end reads it from there and sends it as a header afterwards.

**Coming in v2:** the host will provide a `ui://` resource with a sandboxed
iframe, and control CSP centrally, so no module needs its own web server.
**Loopback will then be marked deprecated with a migration window** — note in
your README that you are on the transitional path.

**Four completion conditions:** the screen must not offer less than whatever it
replaces, its entry point must be findable, it must be operable without the
model, and **its strings must cover nine languages** (zh / en / ja / ko / de /
es / fr / it / pt).

⚠️ **Nine languages is a requirement, not a bonus.** MadCowork's own coverage
is protected by a parity guard; **the strings inside your module are not in
that guard's scope.** They are yours to keep correct.

### 4.1 CSS and JS must be external files — inline ones are refused entirely

The reference `_local_ui.py` sends `style-src 'self'; script-src 'self'`, with
**no `'unsafe-inline'`**. Inline content has no URL, so it can never match any
source-list entry. These four are all refused:

| You write | Result |
|---|---|
| `<style>…</style>` | The whole stylesheet is ignored |
| `<div style="…">` | That attribute is ignored |
| `<script>…</script>` without `src` | Does not execute |
| `<button onclick="…">` | Does not execute |

**This is in the contract because the failure is silent.** The HTML returns
200 with the right byte count, your external `.js` still runs, your data still
arrives — **and the screen renders in the browser's default styling.** Tests at
the byte level cannot see it.

> Measured: the reference module shipped exactly this bug and it survived unit
> tests, the contract checker, an isolated install and a nine-language check —
> **four green lights. It was found by opening a browser and looking.**

**How to detect it:** `document.styleSheets.length`. A refused stylesheet
**never enters that list**; one that applied and was later overridden does.
That single number separates "my CSS is wrong" from "my CSS was rejected".

**How to guard it:** do not write the rule as "inline styles are banned" — the
day the host does allow `'unsafe-inline'`, that guard becomes a false alarm.
Instead assert that **the CSP you send and the HTML you send agree**: parse the
CSP from your own response, and only if `style-src` lacks `'unsafe-inline'`
assert the HTML has no inline styles.

**And the negative condition cannot stand alone:** "no inline styles" is also
satisfied by *having no styles at all* — which is exactly the broken state. So
assert as well that a stylesheet is actually linked and actually served.
`tools/check_contract.py` implements both halves; copy it.

## 5. `mcp.json` — use the sentinel, never an absolute path

```json
{
  "mcpServers": {
    "your-module-server": {
      "command": "madcowork:python",
      "args": ["-c", "bootstrap that derives plugins/<name>/server.py from MADCOWORK_HOME"]
    }
  }
}
```

| Sentinel | Resolves to |
|---|---|
| `madcowork:python` | MadCowork's bundled Python 3.11 |
| `madcowork:node` | The running Electron/node |

**Why:** your user has only a `.dmg` or `.exe`. Their machine may have no
Python at all. An absolute path breaks on the next machine.

⚠️ **Use the standard library only,** or vendor pure-Python dependencies into
your package. **Do not rely on the user's site-packages** — that path breaks
when the host upgrades its Python minor version.

## 6. Naming: the host blocks collisions, you do not have to compute them

Tools are presented as `mcp__<server>__<tool>`. The server name is sanitised
and truncated to **24 characters**; the tool name is truncated to
`64 − len(prefix)`. **Note that server names usually carry a `-module`
suffix**: `madcowork-mail-module` → prefix `mcp__madcowork-mail-module__` (28)
→ tool names limited to **36**.

Truncation used to happen without a collision check, which meant two modules
whose names collided after truncation would **silently overwrite each other's
executor** — a user calling A's tool would run B's code, with no error message.

**The contract now:** **the host must reject modules that collide after
truncation**, naming both modules and the truncated name. You do not have to
compute the budget — but **asserting your naming budget in your own tests** is
worth it, so you find out in your CI rather than on a user's machine.

> The general lesson: **a claim about safety or correctness cannot live inside
> the thing being governed.** "Please be careful, author" is not a mechanism.
> "The host refuses" is.

## 7. Data, updates and recovery

- **Data lives in** `~/.madcowork/module-data/<name>/`. **Removing the module
  does not delete it.** If you offer a way to erase it, make it a separate tool
  that requires confirmation.
- **Update procedure** (the host has no transactional update yet):
  1. Keep the previous `.mcpkg`
  2. Disable → Untrust → Remove (confirm `module-data` survived)
  3. Install the new version → Trust → run your doctor
  4. If it fails, reinstall the previous version
- **Schema versioning is required, not advised:**
  1. Store a `schema_version` alongside your data
  2. **Take a versioned backup before migrating** (for example `notes.sqlite3.v1.bak`)
  3. **When you meet a schema newer than you understand, say so and refuse** —
     never treat it as empty data or misread it
  4. **The previous version must be able to read that backup**

  ⚠️ Without points 2 and 4, step 4 of the update procedure is empty: the old
  version cannot read what the new one wrote, and the user's data is gone.

  If your data is a SQLite database in WAL mode, **use the `conn.backup()` API,
  not a file copy** — un-checkpointed pages are not in the main file, so `cp`
  produces a backup that is missing recent writes, and you only discover that
  when you actually need it.

## 8. What the host guarantees

The host and this repository's checker enforce different layers. Treating them
as interchangeable creates both compatibility bugs and false security claims.

| Rule | MadCowork 0.61.0 host | `check_contract.py` |
|---|---|---|
| Install state | Installs enabled but untrusted; withholds plugin MCP, hooks, and skills until Trust | Not applicable |
| Manifest shape | Requires `plugin.json.name`; validates optional `minimumHostVersion` | Requires and validates the full reference-profile manifest, including SemVer, `moduleApiVersion`, repository, invariant, limitations, and entry points |
| Host compatibility | Refuses a package whose present `minimumHostVersion` exceeds the running host | Validates field syntax only |
| Tool-name collision | Blocks wrapped-name collisions after prefixing/truncation | Checks what can be proven from one package |
| Screen discovery | Looks for a model-visible tool ending in `_open_ui` whose non-error result is a JSON object containing an allowed loopback `url`; does not read `entryPoints` | Requires the reference UI and validates `entryPoints.ui.open` against the `_open_ui` convention |
| Tool approval | Marks plugin MCP tools unsafe and applies the user's action policy | Not applicable |
| Runtime isolation | Filters the child environment but launches local stdio code as the OS user; no filesystem or network sandbox | Warns through this contract; cannot sandbox code |
| Invariant, panel, CSP, i18n, limitations | Not comprehensively revalidated at install | Enforced by the checker |

Revoking Trust through the running app's settings reconciles plugin servers.
The CLI writes the registry but tells users that a running app may need a
restart or a settings toggle before the new state is applied. Do not promise
that every untrust path stops an already running process immediately.

`moduleApiVersion`, native `entryPoints` consumption, `ui://`, and a bundled
`madcowork plugin check` are forward-looking interfaces. This repository may
define and test them, but must label them as checker rules or planned host work
until the flagship consumes them.

The author remains responsible for what Trusted code does. No checker or action
prompt converts same-user execution into confinement.

## 9. How you know you got it right

1. Someone can take this contract and the template and build an installable
   module **without asking us anything**.
2. Declaring a `minimumHostVersion` above the user's host gets the install
   **refused, with a message that names the gap**.
3. After an update, old data still reads; reinstalling the old version also reads.
4. When your module breaks, the app still starts and the error names your module.

## 10. Runtime invariant: have one, or say why you do not

`plugin.json` must carry `runtimeInvariant`, in one of two forms:

```jsonc
"runtimeInvariant": { "module": "invariant", "entry": "check" }
// or
"runtimeInvariant": "none: this module holds no state across calls; it formats its input and returns it"
```

In the first form, `<module>.py` exports `check(home: Path) -> list[str]`
returning failure descriptions — an empty list means healthy.

**Assert a relationship you own, not that something exists.** "`create_draft`
is defined" is not an invariant: it is a static fact that is always true. A
good invariant **can go red because real data got corrupted** — a schema
version that no longer matches the code, a stored value that no longer
validates, an index that disagrees with its contents.

**`check()` must never raise.** A reporter that throws leaves the caller unable
to distinguish "checked and fine" from "the check itself broke".

**How it is verified:** `tools/check_contract.py` **actually imports and calls
it** against a clean temporary `MADCOWORK_HOME`, and requires a `list` back
without an exception. Checking only that the file exists and the function is
defined is not enough — **a guard that is never called is no different from no
guard, and worse, because it reports safety.**

⚠️ **The half the checker cannot verify is yours:** a `check()` that always
returns `[]` passes. Write tests that **corrupt real data** and assert it goes
red. The reference module has five such tests.

## 11. Known Limitations: write down what you cannot do

`README.md` must contain a `## Known Limitations` section with at least one
concrete entry, or `plugin.json` must carry
`"knownLimitations": "none: <concrete reason>"`.

**An empty heading counts as a failure** — it reads as though the question was
considered when it was not.

> An optimistic silence is read downstream as a guarantee. A limitation you
> wrote down is an honest interface.

## 11b. The panel channel: be agent-driven, not a dashboard

A module with tools and a screen still has two pipes that never meet. The
model reads your data and can open your screen, but cannot see what is on it
or change it; the person looking at the screen cannot hand anything back.
Ship a **panel channel** and they meet.

`template/_panel.py` is the reference implementation — vendor it, don't
reinvent it. It gives you three model-facing calls and two that belong to
your page:

| Call | Who uses it | What it does |
|---|---|---|
| `focus({tab})` | the model | points the panel at a tab, so the user sees what is being discussed |
| `note({title, lines, level})` | the model | puts a card at the top of the panel |
| `state({})` | the model | reports which tab the user is on, and whether the panel is open at all |
| `pull({state})` | your page | fetches pending focus/cards and reports what it is showing |
| `dismiss({})` | your page | clears the cards |

Four rules the host expects you to keep:

1. **`pull` and `dismiss` never appear in `tools/list` — and your dispatch
   must enforce that, not merely observe it.** They are the page's plumbing;
   a model that can clear its own cards, or impersonate the page's report,
   has been handed a way to lie about what the user saw.

   Absent from `tools/list` is **not** the same as unreachable. If your
   `handle()` dispatches on the same table your page uses, a model that
   simply names the handler gets it executed. That is not hypothetical: it
   was live in madcowork-hpc until it was measured — naming `hpc_panel_pull`
   over MCP returned a happy result and planted a panel state that never
   happened. Gate the model's dispatch on what the model can see:

   ```python
   MODEL_TOOLS = {entry["name"] for entry in TOOLS}   # after every TOOLS edit

   def handle(name, args):
       if name not in MODEL_TOOLS:                    # not `in HANDLERS`
           raise ValueError(f"unknown tool: {name}")
       return HANDLERS[name](args)
   ```

   The same applies to every workbench-only handler you have — logins,
   destructive buttons, preference writes. The checker cannot see this for
   you: it reads declarations, and this is a property of your dispatch.
2. **A card says who wrote it.** Model prose sitting unmarked next to
   measured numbers is the worst outcome this feature has. `_panel.py`
   records an author; your UI must show it.
3. **Focus is one-shot.** Replayed on every poll it fights the user for the
   tab they just chose.
4. **The poll is local and free.** It must not trigger a backend call, a
   network request or anything a remote site would count as load. A channel
   that costs something per tick is a channel people switch off — and on a
   shared cluster it is a channel that gets your account talked about.

The reverse direction — your page speaking to the chat, so a user can point
at a row and ask about it — is not yours to build: it needs a host bridge,
and it is not available yet. Design your panel so that the model writing a
card is a useful half of the loop on its own.

## 12. Text you return to the model is data, not instructions

1. **Your `skills/` are the one declared instruction channel.** The host
   guarantees they only reach the model after the user trusts you.
2. **Everything your tools return is data.** Do not embed "ignore previous
   instructions" or "you now have permission to…" in a tool result — the host
   treats tool output as untrusted content.
3. **Do not invent framing tags** such as `<skill_instructions>` or `<system>`.
   If you genuinely need text treated as instructions, it goes through the
   skill channel, not smuggled inside a return value.

**Why the distinction holds, and where it does not:** the difference is
provenance and trust policy, **not that skill text is inherently safer**. A
package the user explicitly trusted may use the declared instruction channel.
Tool return values stay untrusted regardless — because a trusted module can
still carry third-party content (email bodies, web pages, files) that nobody
ever trusted. **Trusting a module is not trusting the data it brings in.**
