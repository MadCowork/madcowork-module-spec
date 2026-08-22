#!/usr/bin/env python3
"""Contract self-check — run this in your own CI, not after a user installs.

Some things only the host can decide (whether your tool names collide with
another module's after truncation, whether the running version satisfies your
`minimumHostVersion`) because you cannot know what else is installed. But
**whether your own package is well-formed is checkable before you ship it.**

Checks map to the MadCowork Module Contract v1:
  §2   skills/ are allowed, but tool names must be written the way the model
       sees them (the MCP-wrapped form)
  §3   plugin.json required fields and SemVer format
  §4   a UI must exist, and must survive the CSP it is served under
  §5   mcp.json uses the sentinel, never an absolute path
  §6   tool names fit the truncation budget
  §7   data is not written into the module directory
  §10  a runtime invariant exists, or its absence is explained
  §11  Known Limitations are stated

Usage: python3 check_contract.py [module-directory]
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

MODULE = Path(sys.argv[1] if len(sys.argv) > 1 else "module").resolve()
fails: list[str] = []
warns: list[str] = []


def fail(msg: str) -> None:
    fails.append(msg)


def warn(msg: str) -> None:
    warns.append(msg)


# ── §3 plugin.json ────────────────────────────────────────────────────────
pj_path = MODULE / "plugin.json"
if not pj_path.exists():
    fail("plugin.json is missing")
    pj = {}
else:
    pj = json.loads(pj_path.read_text(encoding="utf-8"))
    for field in ("name", "version", "description", "moduleApiVersion", "minimumHostVersion"):
        if field not in pj:
            fail(f"plugin.json is missing a required field: {field}")
    SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:[-+].*)?$")
    for field in ("version", "minimumHostVersion"):
        v = str(pj.get(field, ""))
        if v and not SEMVER.match(v):
            fail(f"plugin.json {field} is not valid SemVer: {v!r}")

name = str(pj.get("name", ""))

# ── §4 The screen is required ─────────────────────────────────────────────
index_html = MODULE / "ui" / "index.html"
if not index_html.exists():
    fail("ui/index.html is missing — the screen is required, not optional")
else:
    # §4.1 The UI is served under a strict CSP. Inline styles and scripts have
    # no URL, so they can never match a source-list entry and the browser
    # refuses them outright — silently: HTTP 200, correct byte count, the
    # external .js still runs, and only the screen is bare. Byte-level tests
    # cannot see this, so it is blocked statically here rather than discovered
    # after a user installs the package.
    html = index_html.read_text(encoding="utf-8", errors="replace")
    helper = MODULE / "_local_ui.py"
    csp = ""
    if helper.exists():
        m = re.search(r'"Content-Security-Policy",\s*((?:\s*"[^"]*")+)',
                      helper.read_text(encoding="utf-8"))
        if m:
            csp = "".join(re.findall(r'"([^"]*)"', m.group(1)))

    def allows_inline(directive: str) -> bool:
        # With no parsable CSP, assume the strict policy the contract mandates
        # (a false alarm is cheaper than a missed one)
        if not csp:
            return False
        table = {}
        for chunk in csp.split(";"):
            tokens = chunk.split()
            if tokens:
                table[tokens[0].lower()] = tokens[1:]
        return "'unsafe-inline'" in table.get(directive, table.get("default-src", []))

    if not allows_inline("style-src"):
        if "<style" in html:
            fail("ui/index.html has a <style> block — style-src does not allow "
                 "'unsafe-inline', so it is silently refused (HTTP 200, bare screen)")
        if re.search(r'\sstyle\s*=\s*["\']', html):
            fail("ui/index.html has an inline style= attribute — also refused by CSP; use a class from an external stylesheet")
    if not allows_inline("script-src"):
        for tag in re.findall(r"<script\b[^>]*>", html):
            if "src=" not in tag:
                fail(f"ui/index.html has an inline <script> — CSP refuses it: {tag}")
        if re.search(r'\son[a-z]+\s*=\s*["\']', html):
            fail("ui/index.html has an on…= event attribute — CSP refuses it; use addEventListener or .onclick")

    # The negative condition cannot stand alone: "no inline styles" is also
    # satisfied by having no styles at all — which is exactly what a refused
    # stylesheet looks like. So require that one is linked and actually there.
    sheets = re.findall(r'<link[^>]*rel=["\']stylesheet["\'][^>]*href=["\']([^"\']+)["\']', html)
    if not sheets:
        fail("ui/index.html links no stylesheet — the screen will render in browser defaults")
    for href in sheets:
        if "//" in href:
            fail(f"stylesheet points at a remote origin: {href} — CSP allows 'self' only, and modules must work offline")
            continue
        sheet = MODULE / "ui" / href.lstrip("./")
        if not sheet.is_file():
            fail(f"linked stylesheet does not exist: {href}")
        elif sheet.stat().st_size < 500:
            fail(f"linked stylesheet is suspiciously small: {href} ({sheet.stat().st_size} bytes)")

# ── §5 mcp.json must use the sentinel ─────────────────────────────────────
mj_path = MODULE / "mcp.json"
server_names: list[str] = []
if not mj_path.exists():
    fail("mcp.json is missing")
else:
    mj = json.loads(mj_path.read_text(encoding="utf-8"))
    servers = mj.get("mcpServers", {})
    server_names = list(servers)
    if not server_names:
        fail("mcp.json defines no server")
    for sname, spec in servers.items():
        cmd = str(spec.get("command", ""))
        if not cmd.startswith("madcowork:"):
            fail(f"server {sname!r} command is not a sentinel: {cmd!r} — an absolute path breaks on the next machine")
        blob = json.dumps(spec, ensure_ascii=False)
        for bad in ("/Users/", "/home/", "C:\\\\", "/opt/homebrew"):
            if bad in blob:
                fail(f"server {sname!r} config contains a developer-machine path: {bad}")

# ── §6 Tool-name budget ───────────────────────────────────────────────────
# Host side: the server name is sanitised and truncated to 24 chars; the tool
# name is truncated to 64 - len(prefix). Collisions are the host's job to
# refuse (contract §6), but the length budget is yours to respect.
server_py = MODULE / "server.py"
if server_py.exists() and server_names:
    src = server_py.read_text(encoding="utf-8")
    tools = re.findall(r'"name":\s*"([a-z0-9_]+)"', src)
    for sname in server_names:
        wrapped = re.sub(r"[^a-zA-Z0-9_-]", "_", sname)[:24] or "server"
        prefix = f"mcp__{wrapped}__"
        budget = 64 - len(prefix)
        over = sorted({t for t in tools if len(t) > budget})
        if over:
            fail(f"tool names exceed the budget (server {sname!r} → limit {budget}): {', '.join(over)}")
        elif tools:
            longest = max(tools, key=len)
            head = budget - len(longest)
            if head < 4:
                warn(f"only {head} characters of headroom left (longest is {longest}) — adding tools later will overflow")

# ── §7 Data must not be written into the module directory ─────────────────
if server_py.exists():
    src = server_py.read_text(encoding="utf-8")
    if "module-data" not in src:
        warn("server.py never mentions module-data — data belongs in ~/.madcowork/module-data/<name>/")
    if re.search(r'Path\(__file__\)[^\n]*\.(write_text|open\([^)]*[wa])', src):
        fail("server.py appears to write into the module directory — that data disappears when the module is removed")

# ── §2 skills/ are allowed; check they are written correctly ───────────────
# The old rule banned skills/ entirely, because the host filtered on `enabled`
# rather than `trusted`. The host now filters on trust, so the ban is lifted —
# but it brings a new failure mode:
#
#   The model does not see the bare name `mail_create_draft`. It sees
#   `mcp__<sanitised server, 24 chars>__mail_create_draft`.
#   A skill that names only the bare tool sends the model looking for something
#   that does not exist — and that failure looks exactly like "the model
#   ignores my module", with no error message anywhere.
SKILL_DIR = MODULE / "skills"
if SKILL_DIR.exists():
    skill_files = sorted(SKILL_DIR.rglob("*.md"))
    if not skill_files:
        fail("skills/ exists but contains no .md — an empty directory still makes the host think you declare a skill capability")

    # Read the tool names actually registered in server.py.
    #
    # ⚠️ Do not recognise only one style. Three real modules declare tools three
    # different ways:
    #   "name": "mail_doctor",        (spec dict)
    #   tool("quotation_doctor", …)   (builder function)
    #   "xxx_yyy": handler            (dispatch dict)
    # An earlier version recognised only the first, found zero tools in the
    # other two modules, and then reported "none of your tools exist" for every
    # tool mentioned in their skills — dozens of false accusations.
    # **A checker that misjudges is worse than no checker: it sends people to
    # fix things that were never broken.**
    def extract_tools(src: str) -> set[str]:
        pats = (
            r'"name":\s*"([a-z][a-z0-9_]*)"',            # spec dict
            r'\btool\(\s*"([a-z][a-z0-9_]*)"',            # builder function
            r'^\s*"([a-z][a-z0-9_]*)"\s*:\s*[A-Za-z_]',   # dispatch dict
        )
        found: set[str] = set()
        for pat in pats:
            found |= set(re.findall(pat, src, re.M))
        # Keep only things shaped like tool names (they contain an underscore)
        return {f for f in found if "_" in f}

    declared_tools = extract_tools(server_py.read_text(encoding="utf-8")) if server_py.exists() else set()

    # If the declarations cannot be read, say so — never turn that into an
    # accusation against the module.
    tools_readable = bool(declared_tools)
    if server_py.exists() and not tools_readable:
        fail("could not recognise any tool declaration in server.py — **this "
             "means the checker cannot read your style, not that your tools are "
             "missing**. Skill tool-name matching was skipped; please report how "
             "you declare tools so it can be added to extract_tools()")
    wrapped = {}
    for sname in server_names:
        san = re.sub(r"[^a-zA-Z0-9_-]", "_", sname)[:24] or "server"
        prefix = f"mcp__{san}__"
        for tool in declared_tools:
            wrapped[tool] = prefix + tool[:max(1, 64 - len(prefix))]

    for f in skill_files:
        text = f.read_text(encoding="utf-8", errors="replace")
        if not text.lstrip().startswith("---"):
            fail(f"{f.relative_to(MODULE)} has no YAML frontmatter — the host reads name and description from it")
        # Every token in the skill that looks like one of this module's tools
        # must actually exist.
        #
        # ⚠️ "Looks like" is a heuristic, and a heuristic's errors always run in
        # the direction of false accusation. A real case: `hpc_env.json` (a
        # config filename) was reported as "nonexistent tool hpc_env" because it
        # starts with a known prefix. So exclude the obviously-not-a-tool shapes
        # first: anything carrying a file extension, or sitting inside a path.
        # **A guard should miss rather than accuse** — someone who is missed
        # finds out eventually; someone falsely accused goes and changes
        # something that was already correct.
        NOT_A_TOOL = re.compile(r"[a-z][a-z0-9_]*\.(json|md|py|js|sh|txt|ya?ml|db|sqlite3?)\b|/[a-z0-9_.-]*")
        non_tool_spans = {m.group(0) for m in NOT_A_TOOL.finditer(text)}
        for mentioned in set(re.findall(r"\b([a-z][a-z0-9]*_[a-z0-9_]+)\b", text)):
            if any(mentioned in span for span in non_tool_spans):
                continue  # part of a filename or a path, not a tool
            if mentioned in declared_tools:
                if wrapped.get(mentioned) and wrapped[mentioned] not in text:
                    fail(f"{f.relative_to(MODULE)} names the bare tool {mentioned!r}, "
                         f"but the model sees {wrapped[mentioned]!r} — write the wrapped "
                         f"name or the model will not find it")
            elif tools_readable and mentioned.startswith(tuple(f"{t.split('_')[0]}_" for t in declared_tools) or ("\0",)):
                fail(f"{f.relative_to(MODULE)} mentions {mentioned!r}, but server.py "
                     f"registers no such tool — the model will call it and fail")

        # The wrapped form needs its own scan — the regex above cannot see it.
        # In `mcp__srv__mail_missing` the character before `mail_missing` is an
        # underscore, which is a word character, so `\b` never matches and the
        # whole wrapped name is invisible to that loop.
        # Found by a counter-test: changing `__mail_doctor` to `__mail_missing`
        # still produced 0 FAIL. The original mutation test used a *bare* name,
        # which happens to be the class the regex does catch — proving one input
        # goes red and assuming the whole class does.
        valid_prefixes = {re.sub(r"[^a-zA-Z0-9_-]", "_", s)[:24] or "server" for s in server_names}
        for srv, tool in set(re.findall(r"mcp__([A-Za-z0-9_-]+)__([a-z][a-z0-9_]*)", text)):
            if srv not in valid_prefixes:
                fail(f"{f.relative_to(MODULE)} wrapped name uses server segment {srv!r}, "
                     f"but mcp.json produces {sorted(valid_prefixes)} — the model will not find it")
            elif tools_readable and tool not in declared_tools:
                fail(f"{f.relative_to(MODULE)} wrapped name points at {tool!r}, "
                     f"but server.py does not register it — the model will call it and fail")

# ── §10 Runtime invariant: have one, or say why you do not ────────────────
#
# What matters is not whether one is declared but **whether the reporter
# actually runs**. Checking only that the file exists and the function is
# defined repeats a mistake worth naming: a guard that is never called is no
# different from no guard — and worse, because it reports safety. So this
# **imports and calls it** once, for real.
# Non-English entries are deliberate: an author writing "none: 無" is giving an
# empty excuse in their own language, and the check should catch that too.
EMPTY_REASONS = {"n/a", "na", "none", "-", "todo", "tbd",
                 "無", "無需", "不需要", "尚未", "なし", "없음"}
inv = pj.get("runtimeInvariant")
if inv is None:
    fail("plugin.json has no runtimeInvariant — declare one, or state concretely why this module has none")
elif isinstance(inv, str):
    if not inv.startswith("none:"):
        fail(f"runtimeInvariant as a string must start with 'none:' and give a reason, got: {inv!r}")
    else:
        reason = inv[len("none:"):].strip()
        if len(reason) < 20 or reason.lower().rstrip("。.") in EMPTY_REASONS:
            fail(f"the 'none' reason is too short or empty of content ({len(reason)} chars): {reason!r}")
elif isinstance(inv, dict):
    mod_name, entry = str(inv.get("module", "")), str(inv.get("entry", ""))
    src_file = MODULE / f"{mod_name}.py"
    if not mod_name or not entry:
        fail("runtimeInvariant object needs both a module and an entry field")
    elif not src_file.exists():
        fail(f"runtimeInvariant points at a file that does not exist: {src_file.name}")
    else:
        # Run it for real against a clean temporary HOME — prove the reporter
        # is not a shell
        import importlib.util
        import tempfile
        try:
            sys.path.insert(0, str(MODULE))
            spec = importlib.util.spec_from_file_location(f"_inv_{mod_name}", src_file)
            module_obj = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module_obj)
            fn = getattr(module_obj, entry, None)
            if not callable(fn):
                fail(f"runtimeInvariant entry {entry!r} is not callable")
            else:
                with tempfile.TemporaryDirectory() as tmp:
                    result = fn(Path(tmp))
                if not isinstance(result, list):
                    fail(f"{mod_name}.{entry}() must return a list of failure descriptions, got {type(result).__name__}")
        except Exception as exc:
            fail(f"{mod_name}.{entry}() raised — a reporter that throws is no "
                 f"reporter at all: {type(exc).__name__}: {exc}")
        finally:
            if str(MODULE) in sys.path:
                sys.path.remove(str(MODULE))
else:
    fail(f"runtimeInvariant has an invalid type: {type(inv).__name__}")

# ── §11 Known Limitations: write down what you cannot do ──────────────────
# An optimistic silence is read downstream as a guarantee. Making this a gate
# is what gives authors permission to write the uncomfortable sentence —
# "our sandbox is not a real sandbox" — instead of leaving it unsaid.
kl = pj.get("knownLimitations")
readme = MODULE / "README.md"
if isinstance(kl, str) and kl.startswith("none:"):
    reason = kl[len("none:"):].strip()
    if len(reason) < 20 or reason.lower().rstrip("。.") in EMPTY_REASONS:
        fail(f"the knownLimitations 'none' reason is too short or empty of content: {reason!r}")
elif not readme.exists():
    fail("module/README.md is missing — there is nowhere to state Known Limitations")
else:
    text = readme.read_text(encoding="utf-8", errors="replace")
    # Accept the heading in several languages. Recognising English only raises
    # a false alarm against a perfectly good README written in another one —
    # measured: a module already had `## 已知限制` and the gate was too narrow.
    m = re.search(r"^##+\s*(Known Limitations|已知限制|既知の制限)\b.*$", text, re.M)
    if not m:
        fail("module/README.md has no `## Known Limitations` section — if there "
             "genuinely are none, declare knownLimitations: 'none: <reason>' in plugin.json")
    else:
        rest = text[m.end():]
        nxt = re.search(r"^##+\s", rest, re.M)
        body = rest[:nxt.start()] if nxt else rest
        items = [b.strip()[2:].strip() for b in body.splitlines() if b.strip().startswith("- ")]
        if not items:
            fail("the `## Known Limitations` section is empty — an empty heading is worse than none, because it reads as though the question was considered")
        else:
            short = [i for i in items if len(i) < 15]
            if short:
                fail(f"Known Limitations entries are too short to say anything (<15 chars): {short[:2]}")

# ── Declared entry points (§3b) and the panel channel (§11b) ─────────────
# The module names its entry points and this verifies the names resolve. It
# used to infer the channel from tool-name suffixes and got it wrong twice in
# one day — a builder-style module was told it had no channel, and correctly
# hidden plumbing was reported as leaked. A heuristic that misjudges sends
# authors to "fix" what is already right, so the only guessing left is the
# nudge for modules that declared nothing at all.
if server_py.exists():
    src_text = server_py.read_text(encoding="utf-8")
    spec_style = re.findall(r'"name":\s*"([a-z0-9_]+)"', src_text)
    builder_style = re.findall(r'\btool\(\s*"([a-z0-9_]+)"', src_text)
    tool_names = set(spec_style) | set(builder_style)
    caps = pj.get("entryPoints")
    if caps is not None and not isinstance(caps, dict):
        fail("entryPoints must be an object (§3b)")
        caps = {}
    caps = caps or {}

    declared: list[tuple[str, str]] = []
    for group, keys in (("ui", ("open",)), ("panel", ("focus", "note", "state"))):
        block = caps.get(group)
        if block is None:
            continue
        if not isinstance(block, dict):
            fail(f"entryPoints.{group} must be an object naming your tools (§3b)")
            continue
        for key in keys:
            value = block.get(key)
            if value is None:
                if group == "panel":
                    fail(f"entryPoints.panel is declared without `{key}` — name all three, or none (§11b)")
                continue
            if not isinstance(value, str) or not value:
                fail(f"entryPoints.{group}.{key} must be the name of one of your tools (§3b)")
                continue
            declared.append((f"{group}.{key}", value))

    # `tool_name`, not `name`: `name` is the module's own name further up, and
    # shadowing it renamed the module in this script's own report.
    for where, tool_name in declared:
        if tool_name not in tool_names:
            fail(f"entryPoints.{where} names `{tool_name}`, which is not in your tools — "
                 "a declaration that does not resolve is worse than none (§3b)")

    if (MODULE / "ui").is_dir():
        if "panel" not in caps:
            warn("this module has a UI but declares no panel channel (§11b): the model "
                 "cannot see or steer what the user is looking at. Vendor template/_panel.py "
                 "and declare entryPoints.panel if you want it.")
        if "ui" not in caps:
            warn("this module has a UI but does not declare entryPoints.ui.open (§3b): the "
                 "host cannot offer a button for it and has to hope the model picks the right tool.")
        # The one thing that is dangerous rather than merely undeclared.
        leaked = sorted(n for n in tool_names if n.endswith(("panel_pull", "panel_dismiss")))
        if leaked:
            fail(f"panel plumbing must not be model-visible (§11b): {leaked}")

# ── Secret scan (the Python `secrets` module is a known false positive) ────
SECRET = re.compile(r'(api[_-]?key|password|client[_-]?secret)\s*[:=]\s*["\']([^"\']{8,})', re.I)
# A UI label is not a credential. `loginPassword: "Password"` and its nine
# translations are prose: letters, spaces and punctuation, no digits or
# symbols. Real secrets are keys, tokens and passwords — they carry digits or
# symbols essentially always. Skipping prose loses the pathological
# all-lowercase-words passphrase; that miss is the right trade, because a
# checker that accuses correct code sends people to "fix" what is already
# right, and every module with a login field would hit this.
PROSE = re.compile(r"^[^\W\d_][\w \-\u2018\u2019'.,:;!?()\u3000-\u303f\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]*$", re.U)
def is_prose(value: str) -> bool:
    if re.search(r"\d", value) or not PROSE.match(value):
        return False
    # Labels are words; secrets are long unbroken tokens. Split on whitespace
    # and hyphens (compound labels are everywhere: "Palavra-passe",
    # "one-time code") and treat any chunk longer than a long word as a token.
    return all(len(chunk) <= 12 for chunk in re.split(r"[\s\-\u2010-\u2015]+", value) if chunk)
for f in MODULE.rglob("*"):
    if f.is_file() and f.suffix in {".py", ".json", ".js", ".html", ".md"}:
        for i, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            for m in SECRET.finditer(line):
                if is_prose(m.group(2)):
                    continue
                fail(f"possible hard-coded secret: {f.relative_to(MODULE)}:{i}")
                break

# ── Result ────────────────────────────────────────────────────────────────
print(f"Module contract check: {name or MODULE.name}")
for w in warns:
    print(f"  WARN  {w}")
for f_ in fails:
    print(f"  FAIL  {f_}")
print(f"  ── {len(fails)} FAIL / {len(warns)} WARN")
sys.exit(1 if fails else 0)
