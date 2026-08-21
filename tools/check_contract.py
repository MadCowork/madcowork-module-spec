#!/usr/bin/env python3
"""模組契約自我檢查 —— 在自己的 CI 跑,不要等使用者裝進去才發現。

host 端會擋的事(截斷後撞名、minimumHostVersion 不符),模組作者無從得知
其他模組叫什麼名字,但**自己這一包合不合規**是可以先驗的。

檢查項目對應《MadCowork 模組契約 v1》:
  §2  skills/ 可以帶(2026-08-16 解禁),但工具名必須寫 host 包裝後的 wrapped 名
  §3  plugin.json 五個必填欄位 + SemVer 格式
  §4  必須有 UI(鐵律)
  §5  mcp.json 用哨兵,不得寫絕對路徑
  §6  工具名在截斷預算內(host 會擋撞名,但長度是自己該顧的)
  §7  不得把資料寫進模組目錄(要用 module-data)

用法:python3 scripts/check_contract.py [模組目錄]
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
    fail("plugin.json 不存在")
    pj = {}
else:
    pj = json.loads(pj_path.read_text(encoding="utf-8"))
    for field in ("name", "version", "description", "moduleApiVersion", "minimumHostVersion"):
        if field not in pj:
            fail(f"plugin.json 缺欄位:{field}")
    SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:[-+].*)?$")
    for field in ("version", "minimumHostVersion"):
        v = str(pj.get(field, ""))
        if v and not SEMVER.match(v):
            fail(f"plugin.json 的 {field} 不是合法 SemVer:{v!r}")

name = str(pj.get("name", ""))

# ── §4 UI 是必要的 ────────────────────────────────────────────────────────
index_html = MODULE / "ui" / "index.html"
if not index_html.exists():
    fail("缺 ui/index.html —— UI 是鐵律,不是選配")
else:
    # §4.1 UI 是在嚴格 CSP 之下送出的:行內樣式/腳本沒有 URL,匹配不到任何
    # source-list 條目,會被瀏覽器整段拒用 —— 而且是靜默拒用:HTTP 200、
    # 位元組數正確、外部 .js 照跑,只有畫面是裸的。位元組層的測試看不見這件事,
    # 所以在這裡靜態擋掉,不要讓模組作者裝進去才發現。
    html = index_html.read_text(encoding="utf-8", errors="replace")
    helper = MODULE / "_local_ui.py"
    csp = ""
    if helper.exists():
        m = re.search(r'"Content-Security-Policy",\s*((?:\s*"[^"]*")+)',
                      helper.read_text(encoding="utf-8"))
        if m:
            csp = "".join(re.findall(r'"([^"]*)"', m.group(1)))

    def allows_inline(directive: str) -> bool:
        # 沒有可解析的 CSP 時,一律以契約規定的嚴格政策為準(寧可誤紅不可漏綠)
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
            fail("ui/index.html 有 <style> 區塊 —— CSP style-src 不含 'unsafe-inline',"
                 "會被靜默拒用(HTTP 200 但畫面全裸)")
        if re.search(r'\sstyle\s*=\s*["\']', html):
            fail("ui/index.html 有 style= 行內屬性 —— 同樣被 CSP 拒用,改用外部樣式表的 class")
    if not allows_inline("script-src"):
        for tag in re.findall(r"<script\b[^>]*>", html):
            if "src=" not in tag:
                fail(f"ui/index.html 有行內 <script> —— CSP 會拒用:{tag}")
        if re.search(r'\son[a-z]+\s*=\s*["\']', html):
            fail("ui/index.html 有 on…= 事件屬性 —— CSP 會拒用,改用 addEventListener/.onclick")

    # 反面條件不能單獨成立:「沒有行內樣式」用「完全沒有樣式」也達得到,
    # 而那正是被拒用後的實際畫面。所以要求真的外連了樣式表,且檔案有內容。
    sheets = re.findall(r'<link[^>]*rel=["\']stylesheet["\'][^>]*href=["\']([^"\']+)["\']', html)
    if not sheets:
        fail("ui/index.html 沒有外連任何樣式表 —— 畫面會是瀏覽器預設的裸樣子")
    for href in sheets:
        if "//" in href:
            fail(f"樣式表指向外部來源:{href} —— CSP 只允許 'self',且模組必須離線可用")
            continue
        sheet = MODULE / "ui" / href.lstrip("./")
        if not sheet.is_file():
            fail(f"外連的樣式表不存在:{href}")
        elif sheet.stat().st_size < 500:
            fail(f"外連的樣式表過短,疑似空殼:{href}({sheet.stat().st_size} bytes)")

# ── §5 mcp.json 哨兵 ──────────────────────────────────────────────────────
mj_path = MODULE / "mcp.json"
server_names: list[str] = []
if not mj_path.exists():
    fail("mcp.json 不存在")
else:
    mj = json.loads(mj_path.read_text(encoding="utf-8"))
    servers = mj.get("mcpServers", {})
    server_names = list(servers)
    if not server_names:
        fail("mcp.json 沒有定義任何 server")
    for sname, spec in servers.items():
        cmd = str(spec.get("command", ""))
        if not cmd.startswith("madcowork:"):
            fail(f"server {sname!r} 的 command 不是哨兵:{cmd!r} —— 絕對路徑換一台機器就壞")
        blob = json.dumps(spec, ensure_ascii=False)
        for bad in ("/Users/", "/home/", "C:\\\\", "/opt/homebrew"):
            if bad in blob:
                fail(f"server {sname!r} 的設定含開發機絕對路徑:{bad}")

# ── §6 工具名預算 ─────────────────────────────────────────────────────────
# host 端:server 名消毒後截 24;工具名截到 64 - len(prefix)。
# 撞名由 host 擋(契約 v1 §6),但長度是自己該先顧的。
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
            fail(f"工具名超出預算(server {sname!r} → 上限 {budget}):{', '.join(over)}")
        elif tools:
            longest = max(tools, key=len)
            head = budget - len(longest)
            if head < 4:
                warn(f"工具名餘裕僅 {head} 字元(最長 {longest})—— 之後加工具容易超出")

# ── §7 資料不得寫進模組目錄 ────────────────────────────────────────────────
if server_py.exists():
    src = server_py.read_text(encoding="utf-8")
    if "module-data" not in src:
        warn("server.py 未提及 module-data —— 資料應存 ~/.madcowork/module-data/<name>/")
    if re.search(r'Path\(__file__\)[^\n]*\.(write_text|open\([^)]*[wa])', src):
        fail("server.py 疑似寫入模組目錄 —— 移除模組時資料會一起消失")

# ── §2 skills/ 已於 2026-08-16 解禁,改驗「寫對了沒」──────────────────────
# 舊規則是「不得含 skills/」,理由是 host 只看 enabled 不看 trusted。
# host 側已修(trustedPluginSkillDirs),禁令解除 —— 但換來一個新的失敗模式:
#
#   模型在工具清單裡看到的不是裸名 `mail_create_draft`,
#   而是 `mcp__<server 名消毒截 24>__mail_create_draft`。
#   skill 裡只寫裸名,模型就找不到那個工具 —— 而失效的樣子是「模型不理你的模組」,
#   沒有錯誤訊息,查起來很難。
SKILL_DIR = MODULE / "skills"
if SKILL_DIR.exists():
    skill_files = sorted(SKILL_DIR.rglob("*.md"))
    if not skill_files:
        fail("有 skills/ 目錄卻沒有任何 .md —— 空目錄會讓 host 認為你宣告了 skill 能力")

    # 從 server.py 取真正註冊的工具名。
    #
    # ⚠️ 這裡不能只認一種寫法。2026-08-18 實測三個模組:
    #   madcowork-mail        "name": "mail_doctor",        (spec dict)
    #   quotation-suite       tool("quotation_doctor", …)   (builder 函式)
    #   兩者都另有 dispatch 字典 "xxx_yyy": handler
    # 我原本只認第一種,結果對另外兩個模組抓到 0 個工具,
    # 於是把「我讀不到」誤報成「你的工具都不存在」—— 13 條與 15 條誣告。
    # 一個誤判的檢查器比沒有檢查器更糟:它會讓人去修本來就對的東西。
    def extract_tools(src: str) -> set[str]:
        pats = (
            r'"name":\s*"([a-z][a-z0-9_]*)"',            # spec dict
            r'\btool\(\s*"([a-z][a-z0-9_]*)"',            # builder 函式
            r'^\s*"([a-z][a-z0-9_]*)"\s*:\s*[A-Za-z_]',   # dispatch 字典
        )
        found: set[str] = set()
        for pat in pats:
            found |= set(re.findall(pat, src, re.M))
        # 只留看起來像工具名的(有底線、且不是明顯的資料欄位)
        return {f for f in found if "_" in f}

    declared_tools = extract_tools(server_py.read_text(encoding="utf-8")) if server_py.exists() else set()

    # 讀不到就明講讀不到,不要反過來指控模組。
    tools_readable = bool(declared_tools)
    if server_py.exists() and not tools_readable:
        fail("無法從 server.py 辨識任何工具宣告 —— **這是檢查器讀不懂你的寫法,不是你的工具不存在**。"
             "skill 的工具名比對本輪略過;請回報你的宣告方式,以便補進 extract_tools()")
    wrapped = {}
    for sname in server_names:
        san = re.sub(r"[^a-zA-Z0-9_-]", "_", sname)[:24] or "server"
        prefix = f"mcp__{san}__"
        for tool in declared_tools:
            wrapped[tool] = prefix + tool[:max(1, 64 - len(prefix))]

    for f in skill_files:
        text = f.read_text(encoding="utf-8", errors="replace")
        if not text.lstrip().startswith("---"):
            fail(f"{f.relative_to(MODULE)} 缺 YAML frontmatter —— host 靠它取 name 與 description")
        # skill 提到的每個看起來像本模組工具的名字,都必須存在。
        #
        # ⚠️ 但「看起來像」是近似規則,而近似規則的誤判方向永遠是誣告。
        # 2026-08-21:`hpc_env.json`(設定檔名)被判成「不存在的工具 hpc_env」。
        # 所以先把明顯不是工具的形態排除:帶副檔名的、或出現在路徑中的。
        # **守衛寧可漏也不要誣告** —— 漏掉的人會自己發現,被誣告的人會去改對的東西。
        NOT_A_TOOL = re.compile(r"[a-z][a-z0-9_]*\.(json|md|py|js|sh|txt|ya?ml|db|sqlite3?)\b|/[a-z0-9_.-]*")
        non_tool_spans = {m.group(0) for m in NOT_A_TOOL.finditer(text)}
        for mentioned in set(re.findall(r"\b([a-z][a-z0-9]*_[a-z0-9_]+)\b", text)):
            if any(mentioned in span for span in non_tool_spans):
                continue  # 是檔名或路徑的一部分,不是工具
            if mentioned in declared_tools:
                if wrapped.get(mentioned) and wrapped[mentioned] not in text:
                    fail(f"{f.relative_to(MODULE)} 提到裸工具名 {mentioned!r},"
                         f"但模型看到的是 {wrapped[mentioned]!r} —— 請補上 wrapped 名,否則模型找不到")
            elif tools_readable and mentioned.startswith(tuple(f"{t.split('_')[0]}_" for t in declared_tools) or ("\0",)):
                fail(f"{f.relative_to(MODULE)} 提到 {mentioned!r},但 server.py 沒有註冊這個工具 —— "
                     f"skill 指向不存在的工具,模型會照著叫然後失敗")

        # wrapped 形式必須單獨掃 —— 上面那個 regex 看不到它。
        # `mcp__srv__mail_missing` 裡 `mail_missing` 前面是底線(word char),
        # `\b` 不成立,所以整串 wrapped 名對上面的迴圈是隱形的。
        # Codex 2026-08-16 反測:把 `__mail_doctor` 改成 `__mail_missing` 仍 0 FAIL。
        # 我原本的突變測試用的是裸名,剛好落在 regex 抓得到的那一類 ——
        # 證明了一種輸入會響,就當成整類都會響。
        valid_prefixes = {re.sub(r"[^a-zA-Z0-9_-]", "_", s)[:24] or "server" for s in server_names}
        for srv, tool in set(re.findall(r"mcp__([A-Za-z0-9_-]+)__([a-z][a-z0-9_]*)", text)):
            if srv not in valid_prefixes:
                fail(f"{f.relative_to(MODULE)} 的 wrapped 名 server 段是 {srv!r},"
                     f"但 mcp.json 產生的是 {sorted(valid_prefixes)} —— 模型會找不到")
            elif tools_readable and tool not in declared_tools:
                fail(f"{f.relative_to(MODULE)} 的 wrapped 名指向 {tool!r},"
                     f"但 server.py 沒有註冊它 —— 模型會照著叫然後失敗")

# ── §11 執行期不變式:要嘛有,要嘛明講為什麼沒有 ───────────────────────────
# 靈感來自 DeepSeek Harness 的 verify-package-invariants(2026-08-15 研究)。
#
# 關鍵不是「有沒有宣告」,是**reporter 到底會不會跑**。只檢查檔案存在與函式有
# 定義,會複製我們自己犯過的錯:一個從未被呼叫的守衛,跟沒有守衛一樣 ——
# 而且更糟,因為它會回報安全。所以這裡**實際 import 並呼叫**它一次。
EMPTY_REASONS = {"n/a", "na", "無", "none", "無需", "不需要", "-", "尚未", "todo"}
inv = pj.get("runtimeInvariant")
if inv is None:
    fail("plugin.json 缺 runtimeInvariant —— 要嘛聲明一條執行期不變式,要嘛明講為什麼沒有")
elif isinstance(inv, str):
    if not inv.startswith("none:"):
        fail(f"runtimeInvariant 若為字串必須以 'none:' 開頭並附理由,實得:{inv!r}")
    else:
        reason = inv[len("none:"):].strip()
        if len(reason) < 20 or reason.lower().rstrip("。.") in EMPTY_REASONS:
            fail(f"runtimeInvariant 的『沒有』理由過短或是空話({len(reason)} 字元):{reason!r}")
elif isinstance(inv, dict):
    mod_name, entry = str(inv.get("module", "")), str(inv.get("entry", ""))
    src_file = MODULE / f"{mod_name}.py"
    if not mod_name or not entry:
        fail("runtimeInvariant 物件需要 module 與 entry 兩個欄位")
    elif not src_file.exists():
        fail(f"runtimeInvariant 指向的檔案不存在:{src_file.name}")
    else:
        # 真的跑一次 —— 對一個乾淨的臨時 HOME,證明 reporter 不是空殼
        import importlib.util
        import tempfile
        try:
            sys.path.insert(0, str(MODULE))
            spec = importlib.util.spec_from_file_location(f"_inv_{mod_name}", src_file)
            module_obj = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module_obj)
            fn = getattr(module_obj, entry, None)
            if not callable(fn):
                fail(f"runtimeInvariant 的 entry {entry!r} 不可呼叫")
            else:
                with tempfile.TemporaryDirectory() as tmp:
                    result = fn(Path(tmp))
                if not isinstance(result, list):
                    fail(f"{mod_name}.{entry}() 必須回傳 list(失敗描述),實得 {type(result).__name__}")
        except Exception as exc:
            fail(f"執行 {mod_name}.{entry}() 時拋例外 —— 會拋的 reporter 等於沒有:"
                 f"{type(exc).__name__}: {exc}")
        finally:
            if str(MODULE) in sys.path:
                sys.path.remove(str(MODULE))
else:
    fail(f"runtimeInvariant 型別不合法:{type(inv).__name__}")

# ── §12 Known Limitations:把做不到的事寫出來 ──────────────────────────────
# 樂觀的註解會被當成保證。DeepSeek 用 CI 閘門逼每個 package 寫,效果是他們敢寫
# 「我們的 workflow 沙箱不是真沙箱」這種話。
kl = pj.get("knownLimitations")
readme = MODULE / "README.md"
if isinstance(kl, str) and kl.startswith("none:"):
    reason = kl[len("none:"):].strip()
    if len(reason) < 20 or reason.lower().rstrip("。.") in EMPTY_REASONS:
        fail(f"knownLimitations 的『沒有』理由過短或是空話:{reason!r}")
elif not readme.exists():
    fail("缺 module/README.md —— Known Limitations 沒有地方寫")
else:
    text = readme.read_text(encoding="utf-8", errors="replace")
    # 中英文都認 —— 契約的受眾兩種都有,只認英文會對中文 README 產生假紅燈
    # (2026-08-15 實測:本模組原本就有 `## 已知限制`,是閘門寫窄了)
    m = re.search(r"^##+\s*(Known Limitations|已知限制|既知の制限)\b.*$", text, re.M)
    if not m:
        fail("module/README.md 缺 `## Known Limitations` / `## 已知限制` 段落 —— "
             "沒有限制要在 plugin.json 標 knownLimitations: 'none: <理由>'")
    else:
        rest = text[m.end():]
        nxt = re.search(r"^##+\s", rest, re.M)
        body = rest[:nxt.start()] if nxt else rest
        items = [b.strip()[2:].strip() for b in body.splitlines() if b.strip().startswith("- ")]
        if not items:
            fail("`## Known Limitations` 段落是空的 —— 空標題比沒有標題更糟,它看起來像已經想過")
        else:
            short = [i for i in items if len(i) < 15]
            if short:
                fail(f"Known Limitations 有過短的條目(<15 字元):{short[:2]}")

# ── 秘密掃描(排除 Python secrets 模組這類誤報)─────────────────────────────
SECRET = re.compile(r'(api[_-]?key|password|client[_-]?secret)\s*[:=]\s*["\'][^"\']{8,}', re.I)
for f in MODULE.rglob("*"):
    if f.is_file() and f.suffix in {".py", ".json", ".js", ".html", ".md"}:
        for i, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if SECRET.search(line):
                fail(f"疑似寫死的秘密:{f.relative_to(MODULE)}:{i}")

# ── 結果 ──────────────────────────────────────────────────────────────────
print(f"模組契約檢查:{name or MODULE.name}")
for w in warns:
    print(f"  WARN  {w}")
for f_ in fails:
    print(f"  FAIL  {f_}")
print(f"  ── {len(fails)} FAIL / {len(warns)} WARN")
sys.exit(1 if fails else 0)
