# 插件開發指南

給想擴充 MadCowork、或想把自己的系統接進來的開發者。

對照文件:
- **只有封裝檔、想在 app 裡直接做插件** → 不用讀這份,在對話框說「我想做一個插件」,
  內建的 `plugin-authoring` skill 會帶你走完。
- **只想寫一份可重複用的流程文字** → [skills-submodule.md](skills-submodule.md),
  插件是殺雞用牛刀。
- **想知道 MadCowork 內部怎麼跑的** → [madcowork-architecture-zh.md](madcowork-architecture-zh.md)。

---

## 1. 插件是什麼

一個資料夾。裡面一份 `plugin.json`,加上三種能力的任意組合:

```
my-plugin/
  plugin.json      必要
  skills/*.md      markdown playbook —— 純文字
  hooks.json       事件掛鉤        —— 執行程式碼
  mcp.json         MCP server 宣告  —— 執行程式碼
```

`plugin.json` 最小形式,`name` 決定安裝後的目錄名與身分:

```json
{
  "name": "invoice-helper",
  "version": "0.1.0",
  "description": "從 PDF 發票抓出品項與金額,對帳後產出月結表。"
}
```

`name` 受 `/^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$/` 限制。`description` 不是裝飾——
它是模型判斷「這個插件適不適用當前任務」的主要依據,值得認真寫。

安裝後住在 `<MADCOWORK_HOME>/plugins/<name>/`,預設 `~/.madcowork/plugins/`。

## 2. 信任模型(先讀這段)

**安裝 ≠ 可以執行程式碼。** 插件裝好的狀態是 `enabled + untrusted`:

| 能力 | 需要 | 為什麼 |
|---|---|---|
| `skills/` | enabled | 純提示文字,不執行任何東西 |
| `hooks.json` | enabled **+ trusted** | 會在使用者機器上執行程式 |
| `mcp.json` | enabled **+ trusted** | 同上 |

安裝/啟用/信任狀態存在 `plugins/registry.json`,**在所有插件目錄之外**——
所以插件無法藉由改自己的檔案來取得信任。這是刻意的。

其他幾道界線,寫插件時可以放心依賴:

- 插件目錄在 app bundle **之外**。插件碰不到程式本體,也毀不掉它的簽章。
- 插件名稱經 `resolve()` 檢查逃逸,`../` 進不去。
- 手動把資料夾複製進 `plugins/` 會得到 **disabled + untrusted**——registry 沒有
  紀錄,什麼都不會載入,也不會報錯。**永遠走安裝流程,不要教使用者手動複製。**

## 3. 三種能力

### 3.1 skills/ —— 零依賴,先做這個

`skills/<name>.md`,YAML frontmatter 至少要 `name` 和 `description`。
寫法與 bundled skill 相同,見 [skills-submodule.md](skills-submodule.md)。

**優先序是全系統最低的**——比內建指令還低。取名撞到 `compact` 這類內建會被
靜默蓋掉,不會有警告。加上自己的前綴。

### 3.2 mcp.json —— 接外部系統

支援兩種傳輸。**stdio**(在使用者機器上起一支本機程序):

```json
{ "mcpServers": {
    "acme": {
      "command": "madcowork:python",
      "args": ["server.py"],
      "env": { "ACME_MODE": "production" }
    } } }
```

`madcowork:python` 會解析成 app 內建直譯器。插件 stdio server 以安裝後的
插件根目錄為工作目錄,所以 `args` 請使用插件內相對路徑;不要使用 `~`、
`${VAR}` 或作者電腦的絕對路徑。這樣同一顆 `.mcpkg` 才能跨機器安裝。

**remote**(HTTP / SSE):

```json
{ "mcpServers": {
    "acme": {
      "url": "https://api.acme.com/mcp",
      "type": "http",
      "headers": { "Authorization": "Bearer ${ACME_TOKEN}" }
    } } }
```

`type` 只接受 `"http"`(Streamable HTTP,預設)或 `"sse"`,其他值會拋錯。

`headers` 支援 `${VAR}`,由 `expandMcpHeaders` 從 `process.env` 展開。
金鑰要放哪、為什麼,見下一節。

失敗模式要知道:**變數沒設的話整個 header 會被丟掉**,只留一行 log,連線照常
建立。症狀看起來像「server 沒回應」,實際上是沒帶授權標頭。

**名稱衝突:兩個受信任的插件宣告同名 server → 兩邊都被丟掉**,不是誰贏。
被丟掉的清單在 `GET /api/plugins/mcp-conflicts`,Settings 會顯示。
這是刻意的取捨:悄悄被冒名頂替比直接壞掉更糟,因為畫面上什麼都不會變。
**server 名稱請加自己的前綴。**

若插件提供本機工作台,工具名稱必須以 `_open_ui` 結尾,並回傳包含
`{"ok":true,"url":"http://127.0.0.1:…"}` 的 JSON 文字 envelope。這個網址
**只在產生它的模組行程存活期間有效**;模組重啟後 port 或 token 都可能改變。
App 會在對話重新掛載工作台時自動向已啟用、受信任且已連線的 stdio
模組重新索取網址,也會在 loopback 連線遭拒或重設時自癒。重新掛載或
連線失敗時,App 可能多次呼叫同一個 `*_open_ui`。

### 3.3 金鑰放哪(絕對不要寫進 mcp.json)

MadCowork 有**兩個**保管區,插件只碰得到其中一個:

| 保管區 | 存什麼 | 插件 |
|---|---|---|
| `secretVault.mjs` — AES-256-GCM,金鑰由 Electron 主程序用 OS keychain 封裝,並以署名常數 HKDF 綁定 | `accounts.json` / `settings.json`,也就是 **app 自己的供應商金鑰**(Anthropic / OpenAI / …) | ❌ **拿不到,而且這是刻意的** |
| `~/.madcowork/.env` — 開機時由 `loadDotenvIntoProcessEnv()` 載進 `process.env`,並把生效路徑公布為 `MADCOWORK_ENV_PATH` 讓所有子程序一致 | 使用者自己放的變數 | ✅ 見下表 |

第一個拿不到不是缺口,是正確的隔離:第三方插件不該讀得到使用者的
Anthropic key。**你的插件要用自己的金鑰,走第二個。**

使用者可以在對話裡說「設定 API key」,由內建的 `manage-credentials` skill
寫進 `~/.madcowork/.env`;你的 README 只要告訴他們變數名稱就好。

進到 server 的方式**依傳輸而不同**,這點很容易踩:

| 傳輸 | 金鑰路徑 |
|---|---|
| **HTTP / SSE** | `headers` 的 `${VAR}` 會展開 → `.env` 的變數直接可用。**宣告式,首選。** |
| **stdio** | `mcp.json` 的 `env` 是**字面值,不展開**;而且 MCP SDK 只繼承 6 個安全變數(POSIX:`HOME` `LOGNAME` `PATH` `SHELL` `TERM` `USER`)。所以 **`.env` 的變數傳不進去**——請讓 **server 自己去讀 `~/.madcowork/.env`**(它拿得到 `HOME`),或讀 `MADCOWORK_ENV_PATH`。 |

換句話說:stdio 插件把 key 寫進 `mcp.json` 的 `env` 是**唯一會動的做法,也是
最糟的做法**——那份檔案是要分發出去的。多寫五行讓 server 自己讀 `.env`。

### 3.4 hooks.json —— 事件掛鉤

支援的事件:`PreToolUse`、`PostToolUse`、`UserPromptSubmit`、`SessionStart`、
`Stop`、`SubagentStop`、`PreCompact`。

插件的 hooks 掛在**最低層**,而且是**疊加**的——使用者自己的 hooks 照跑,
插件的跟著一起跑,永遠不會取代。所以不要假設自己是唯一的處理者。

## 4. 安裝與管理

三條路,同一套 registry:

**CLI**(有終端機時最快):

```bash
madcowork plugin add <git-url|本機路徑>
madcowork plugin list
madcowork plugin trust <name>
madcowork plugin disable <name>
madcowork plugin remove <name>
```

**Settings UI**:設定 → 安裝插件 → 貼 git URL 或本機路徑 → 安裝。

**HTTP API**(要自動化時):

```
GET  /api/plugins                → { plugins: [...] }
POST /api/plugins                → { action, source?, name? }
     action: add | remove | enable | disable | trust | untrust
GET  /api/plugins/mcp-conflicts  → { conflicts: [...] }
```

每次狀態變更都會 `reconcileMcpServers()`,所以 **untrust / disable / remove 會
立刻收掉正在跑的 MCP server,不需要重開 app**;trust / enable 也是立刻生效。

git 安裝走 `git clone --depth 1` 後刪掉 `.git`——插件不保留版本歷史。
**更新的方式是移除後重裝**,沒有增量更新。

## 5. 分發

給別人用的插件,README 至少要交代四件事:

1. 這個插件會執行什麼(哪支程式、什麼參數、碰什麼資料)——使用者要靠這個
   決定要不要按「信任」。
2. `mcp.json` 裡哪幾行是本機絕對路徑,安裝前必須改。
3. 需要哪些變數、變數名叫什麼、放進 `~/.madcowork/.env`(使用者可以在對話裡
   說「設定 API key」交給 `manage-credentials` 處理),以及沒設會出現什麼症狀。
4. server 名稱前綴,好讓別人避開衝突。

**永遠不要在分發的 `mcp.json` 裡填入真實金鑰**,即使那是唯一「一裝就會動」的
寫法。留變數名 + README 一句話,使用者多花三十秒,你少外洩一把 key。

## 6. 常見的坑

| 症狀 | 原因 |
|---|---|
| 裝好了但什麼都沒發生 | 有 hooks/mcp 卻沒按「信任」 |
| 資料夾在 `plugins/` 裡卻顯示 disabled | 手動複製進去的,registry 沒紀錄——要走安裝 |
| MCP 工具列得出來但呼叫失敗 | server 起不來;**工具出現在清單不代表連得上** |
| 像「server 沒回應」 | `headers` 的 `${VAR}` 沒設,整個 header 被丟掉 |
| stdio server 讀不到我放在 `.env` 的變數 | 這是預期的:SDK 只繼承 6 個安全變數,`mcp.json` 的 `env` 又是字面值。**讓 server 自己讀 `~/.madcowork/.env`** |
| 插件想拿使用者的 Anthropic key | 拿不到,`secretVault` 只給後端自己。**這是刻意的隔離,不是 bug** |
| 換一台機器就壞 | `command`/`args` 是絕對路徑,不會展開 |
| 我的 MCP server 整個消失 | 跟另一個受信任插件撞名,兩邊都被丟 |
| `/我的指令` 叫不出來 | 跟內建同名,插件層優先序最低被蓋掉 |

## 7. 實例

`quotation-suite` 是一個實際在用的插件:`plugin.json` + `skills/quotation.md`
+ `mcp.json` 指向一支本機 python server。它的 `mcp.json` 開頭就放了一行
`_comment` 提醒絕對路徑要隨機器修改——那是上面第五個坑踩出來的,值得照抄。
