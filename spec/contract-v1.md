# MadCowork 模組契約 v1


## 0. 一句話

**模組 = 一個 `.mcpkg` 單檔,裝進 MadCowork 後提供 MCP 工具與自己的 HTML UI,
不碰主程式、不碰使用者憑證,更新時只換這個檔。**

## 1. 你能做什麼、不能做什麼(先講邊界)

| | |
|---|---|
| ✅ 提供 MCP 工具(模型可呼叫) | |
| ✅ 提供 HTML UI(使用者直接操作) | **必要,非選配** —— 見 §4 |
| ✅ 在 `~/.madcowork/module-data/<你的模組名>/` 存資料 | 移除模組不刪它 |
| ❌ 碰 MadCowork 本體或它的簽章 | 模組住在 app 外面 |
| ❌ 拿到使用者的憑證 | stdio env 走 allowlist,vault 金鑰不在內 |
| ❌ 安裝後自動執行 | 裝好是 `enabled + untrusted`,要人按「信任」 |

**模組寫壞了,最慘是那個模組不載入,app 照常開。** 這是刻意的。

## 2. 封包內容

```
你的模組/
  plugin.json      ← 身分與相容性(§3)
  mcp.json         ← 怎麼啟動你的 server(§5)
  server.py        ← 你的工具實作
  ui/index.html    ← 你的畫面(§4)
  README.md  CHANGELOG.md  LICENSE
```

打包成單檔:`madcowork plugin pack <資料夾>` → `<name>-<version>-universal.mcpkg`

**可以包含 `skills/`(解禁)。** host 保證只有**已信任**的插件,
其 skill 才會被模型看見(`pluginRegistry.mjs` 的 `trustedPluginSkillDirs()`
過濾 `enabled && trusted`)。

> **這條原本是「不得包含 skills/」。** 當時的理由是 host 只看 `enabled` 不看 `trusted`,
> 所以未信任插件的 skill 也進得了模型視野。**那個禁令是繞道,不是修好** ——
> 而它的代價是:**沒有 skill,模型不會自然使用你的工具**(工具出現在清單上
> 不等於模型知道何時該用)。host 側已於 2026-08-16 修正並改名,禁令隨之解除。

**skill 要寫對一件事,否則等於沒寫**:模型在工具清單裡看到的**不是你的裸工具名**,
而是 `mcp__<server 名消毒截 24>__<工具名>`。例:

```
你在 server.py 宣告   mail_create_draft
模型實際看到的是      mcp__madcowork-mail-module__mail_create_draft
```

**skill 裡若只寫裸名,模型會找不到那個工具。** 兩種寫法都可以:

1. 寫完整的 wrapped 名(精確,但 server 改名就失效)
2. 描述能力與時機,並註明「工具名以 `<你的前綴>_` 開頭」(較耐改名)

**建議加一條你自己的測試**:斷言 skill 文字裡提到的每個工具名,
都真的存在於 host 包裝後的工具清單裡。**否則改了 server 名或工具名,
skill 會靜默失效 —— 而失效的樣子就是「模型不理你的模組」,查起來很難。**

## 3. `plugin.json`

```json
{
  "name": "your-module",
  "version": "0.1.0",
  "description": "一句話說明",
  "moduleApiVersion": 1,
  "minimumHostVersion": "0.55.0"
}
```

| 欄位 | 規則 |
|---|---|
| `name` | 全域唯一;**同時是工具名前綴的一部分**,見 §6 命名預算 |
| `version` | SemVer。PATCH=修 bug;MINOR=新增向後相容工具/欄位;MAJOR=刪工具、改必要參數、破壞資料格式 |
| `moduleApiVersion` | 目前為 `1` |
| `minimumHostVersion` | **你依賴的最低 MadCowork 版本**。host 會擋住不符的安裝(見 §8)|

## 4. UI 是必要的,不是選配

模組必須提供人可以直接操作的畫面。
只有 MCP 工具的模組**不算完成** —— 那會讓能力被鎖在對話裡。

**現行交付方式(v1,transitional)**:模組跑一個**只聽 `127.0.0.1`** 的極簡 HTTP server,
提供一個工具(例:`<name>_open_ui`)回傳 loopback URL,MadCowork 的 browser panel 會開它。

- **寫入端點必須要 token**:啟動時 `secrets.token_urlsafe()` 產生,以 header
  (參考實作用 `X-MadCowork-Module-Token`)驗證;**無 token 的 POST 回 403**。
- 參考實作:兩個 v0.2.0 模組的 `_local_ui.py` + `ui/index.html`,
  其 `tests/test_module.py` 有「無 token POST → 403、有 token → 成功」的可重現測試。

**未來(v2)**:host 將提供 `ui://` resource + 沙箱 iframe(MCP 標準),CSP 由 host 統一控制,
不再需要每個模組跑自己的 web server。**屆時 loopback 會標為 deprecated 並給遷移窗口** ——
所以請在 README 註明你用的是 transitional 路徑。

**四條完成條件**:畫面清單不縮水(若取代既有功能)、入口找得到、不倚賴模型即可操作、
**字串覆蓋 9 語**(zh / en / ja / ko / de / es / fr / it / pt)。

⚠️ **九語是必要條件,不是加分項。** 覆核時發現兩個參考模組
(`madcowork-hpc`、`quotation-suite` v0.2.0)**目前只有 zh-Hant** —— 這是已知落差,
新模組不得沿用。MadCowork 本體的九語覆蓋有 parity guard 守著,
模組自帶的 HTML 字串**不在那個守衛範圍內**,要自己顧。

**transitional bootstrap(規範原本漏載,依實作補上)**:
loopback UI 的 token 由 `mail_open_ui` 之類的工具**放在回傳 URL 的 query** 交付,
前端取出後改以 `X-MadCowork-Module-Token` header 送出。
這是 v1 的既定做法,`ui://` 到位後會一併取代。

### 4.1 CSS 與 JS 一律外部檔案 —— 行內的會被 CSP 整段拒用

參考實作的 `_local_ui.py` 送出 `style-src 'self'; script-src 'self'`(**不含
`'unsafe-inline'`**)。行內內容沒有 URL,永遠匹配不到任何 source-list 條目,
所以下列四種寫法會被瀏覽器**拒絕執行/套用**:

| 寫法 | 結果 |
|---|---|
| `<style>…</style>` | 整段樣式不套用 |
| `<div style="…">` | 該屬性不套用 |
| `<script>…</script>`(無 `src`) | 不執行 |
| `<button onclick="…">` | 不執行 |

**這條之所以要寫進契約,是因為它的失敗方式是靜默的**:HTML 照樣 200、位元組數
正確、外部 `.js` 照樣跑、資料照樣出來 —— **只有畫面是瀏覽器預設的裸樣子**。
位元組層的測試(HTTP 200 + Content-Length)看不見它。

> 實測:`madcowork-mail` 的 UI 就是這樣壞的,而且撐過了單元測試、
> 契約自檢、隔離安裝、九語檢查四層綠燈,**在瀏覽器裡看第一眼才發現**。

**怎麼驗**:`document.styleSheets.length`。被拒用的樣式表**不會進這個清單**
(被套用後又被覆蓋的會)—— 這一項區分得出「我的 CSS 寫錯」和「我的 CSS 被拒絕」。

**守衛怎麼寫**:不要寫成「禁用行內樣式」這種品味規則(host 哪天真的放行
`'unsafe-inline'`,它就變成假紅燈),要驗**送出的 CSP 與送出的 HTML 一致**:
解析自己回應裡的 CSP,若 `style-src` 不含 `'unsafe-inline'`,就斷言 HTML 無行內樣式。

**反面條件不能單獨成立**:「沒有行內樣式」用「完全沒有樣式」也達得到,
而那正是壞掉後的實際畫面 —— 所以必須同時斷言**確實外連了樣式表、而且真的送得出來**。
`scripts/check_contract.py` 已實作這兩半(五條突變全數轉紅),可直接抄。

## 5. `mcp.json` —— 用哨兵,不要寫絕對路徑

```json
{
  "mcpServers": {
    "your-module-server": {
      "command": "madcowork:python",
      "args": ["-c", "…用 MADCOWORK_HOME 推導 plugins/<name>/server.py 的 bootstrap…"]
    }
  }
}
```

| 哨兵 | 解析成 |
|---|---|
| `madcowork:python` | MadCowork 內建的 Python 3.11 |
| `madcowork:node` | 執行中的 Electron/node |

**為什麼**:使用者只有 `.dmg`/`.exe`,他機器上不一定有 Python。寫絕對路徑 = 換一台機器就壞。

⚠️ **只用 Python 標準庫**,或把純 Python 依賴 vendor 進包。
**不得依賴使用者的 site-packages** —— host 升級 Python 小版本時那條路會斷(2026-08-14 實證)。

## 6. 命名:host 會擋撞名,你不必自己算

工具最終呈現為 `mcp__<server 名>__<工具名>`;server 名消毒後截 **24 字元**,
工具名截到 `64 - prefix 長度`。**注意 server 名通常帶 `-module` 後綴**,
例:`madcowork-mail-module` → prefix `mcp__madcowork-mail-module__`(28)→ 工具名上限 **36**。

⚠️ **本節原本寫「上限 43,請你自己算」—— 那是錯的做法,已改。**

實測(由 host 實作)發現:**截斷後不檢撞名**,
`rebuildToolList` 會留下重名 specs,而工具 map **由最後一筆覆蓋 executor** ——
synthetic 反測得到兩個不同 server 的 wrapped name 完全相同、`collision=true`。

**後果**:兩個外部模組截斷後同名時,**後載入的會靜默劫持前一個的工具** ——
使用者呼叫 A 的工具,跑的是 B 的程式碼,而且沒有任何錯誤訊息。

**契約(修正後)**:**host 必須拒絕截斷後重名的模組**,並在拒絕訊息中列出撞到的兩個模組
與截斷後的名字。開發者不必自己算 —— 但**建議把命名預算寫成你模組測試裡的斷言**
(參考 `madcowork-mail` 的 `test_tools_are_registered`),這樣你在自己的 CI 就會先發現,
而不是等使用者裝進去才撞。

> 這條的教訓通用:**安全與正確性的宣告不能寫在被管制的一方身上。**
> 「請作者小心」不是機制,「host 拒絕」才是。

## 7. 資料、更新與回復

- **資料**:`~/.madcowork/module-data/<name>/`。**移除模組不刪資料**;要清除請提供獨立且需確認的工具。
- **更新流程**(host 目前無交易式更新):
  1. 保留上一版 `.mcpkg`
  2. Disable → Untrust → Remove(確認 `module-data` 仍在)
  3. Install 新版 → Trust → 跑你的 doctor
  4. 失敗就重裝上一版
- **schema 版本化(必要條件,非建議)**:
  1. 資料存一個 `schema_version`;
  2. **新版首次啟動先做 versioned backup**(例:`mail.sqlite3.v1.bak`)再遷移;
  3. **遇到比自己新的 schema 必須明講並拒絕**,不得當成空資料或誤讀
     (參考 `madcowork-mail` 的 `test_newer_schema_is_refused_not_misread`);
  4. **上一版必須讀得回自己的 backup** —— 這是回復流程能成立的前提。

  ⚠️ 覆核時發現兩個參考模組 v0.2.0 **尚無 versioned backup 與 rollback migration**
  —— 已知落差,新模組不得沿用。**沒有第 2、4 點,§7 的「失敗就重裝上一版」是空的**:
  舊版讀不回新版寫過的資料,使用者的東西就回不來了。

## 8. host 端的保證

本契約中所有寫「必須」的條目,**由 host 執行,而不是仰賴作者自律**:

- 安裝時驗證 `plugin.json` 的欄位與 SemVer 格式,不符即拒絕安裝
- 比對 `minimumHostVersion` 與實際版本,不符即拒絕並同時列出兩邊版本
- 檢查工具名截斷後是否與既有模組相撞;**相撞時兩邊都不發布**,
  而不是讓安裝順序決定誰贏
- 未信任的模組:hooks、MCP server 與 skills 一律不載入;
  取消信任立即生效,不需重啟
- 子行程環境走 allowlist,你的模組拿不到使用者的憑證

> 這條清單的意義是:**你不需要「小心」才能安全。**
> 你寫壞了,最壞的結果是你的模組不載入,而使用者的 app 照常開。

## 9. 驗收(給我們自己的)

外部開發者體驗算過關,要能做到:

1. 拿本規範 + 參考實作,**不問我們任何問題**就能做出一個可安裝的模組。
2. 宣告 `minimumHostVersion` 高於使用者的 host 時,**安裝被擋且訊息說得出差在哪**。
3. 模組更新後,舊資料讀得回;回裝舊版也讀得回。
4. 模組壞掉時,app 照常開,錯誤訊息指得出是哪個模組。

---

## 10. 待 覆核者 覆核

1. **§8 第 1 條**:`minimumHostVersion` 裝檢要放在 `addPlugin` 哪一步?我只確認「讀取 = 0 次」,沒設計插入點。
2. **§4 的 v1→v2 遷移窗口**:你判斷 `ui://` 什麼時候該讓 loopback deprecated?過早會打斷外部開發者。
3. **§6 命名預算**:我從 host 端 推得 24/64,**請確認截斷後撞名的行為**(兩個模組截斷後同名會怎樣)。
4. 本規範有沒有跟你 v0.2.0 的實際做法**不一致**的地方?以你的實作為準,我改規範。

## 11. 執行期不變式:要嘛有,要嘛明講為什麼沒有(新增)

**你的模組跑起來之後,自己知不知道自己壞了?**

`plugin.json` 必填 `runtimeInvariant`,二選一:

```jsonc
"runtimeInvariant": { "module": "invariant", "entry": "check" }
// 或
"runtimeInvariant": "none: 本模組不持有跨呼叫狀態,只把輸入格式化後回傳"
```

形式 A 時,`<module>.py` 匯出 `check(home: Path) -> list[str]`,回傳失敗描述(空 = 通過)。

**斷言的必須是你自己擁有的關係,不是「某個函式存不存在」。**
「`create_draft` 有定義」不是不變式 —— 那是靜態事實,而且永遠成立。
好的不變式**能因為真實的資料損壞而轉紅**:schema 版本與程式碼常數不一致、
存進去的值今天驗不過、索引與內容對不起來。

`check()` **絕不能拋例外** —— 呼叫端分不出「檢查通過」與「檢查自己壞了」。

**閘門怎麼驗**:`scripts/check_contract.py` **實際 import 並呼叫它一次**
(對一個乾淨的臨時 `MADCOWORK_HOME`),要求回傳 `list` 且不拋。
**只檢查「檔案存在、函式有定義」是不夠的** —— 一個從未被呼叫的守衛跟沒有守衛一樣,
而且更糟,因為它會回報安全。

⚠️ **閘門證明不了的那一半要你自己補**:一個永遠回傳 `[]` 的 `check()` 也會通過。
請在你自己的測試裡**製造真的資料損壞**,斷言它會響。參考實作有五條這樣的測試。

## 12. Known Limitations:把做不到的事寫出來(新增)

`module/README.md` 必須有 `## Known Limitations` 或 `## 已知限制` 段落,
至少一條具體條目(≥ 15 字元);真的沒有就在 `plugin.json` 標
`"knownLimitations": "none: <具體理由>"`。

**空標題視為失敗** —— 它看起來像已經想過。

> 這條抄自 DeepSeek Harness 的 `verify-package-readme-limitations`。
> 效果很明顯:有閘門逼著,他們敢在 README 寫「我們的 workflow 沙箱不是真沙箱」、
> 「這個 POC 不支援放在沙箱預設環境變數裡的秘密」。
> **一句樂觀的註解會被下游當成保證;寫出來的限制才是誠實的介面。**

## 13. 你回傳給模型的文字是「資料」,不是「指令」(新增)

三條:

1. **`skills/` 可以放(§2 已於 解禁)**,但它是**唯一**被承認的指令通道 ——
   host 保證它只在使用者按下信任之後才進入模型視野。
   ⚠️ 本條初稿寫「封包不得含 `skills/`」,與 §2 直接矛盾,已修正。
   **同一份契約裡兩處講反,比只講錯一次更糟:讀的人會照著他先看到的那一處做。**
2. **模組回傳給模型的文字預設是資料。** 不要在工具回傳值裡夾帶
   「請忽略先前指示」「你現在有權限……」這類語句 —— host 會把它當成不可信內容處理。
3. **模組不得自造框架標籤**(如 `<skill_instructions>`、`<system>`)。
   若你的模組確實要提供「該被當成指令」的文字,**必須經由 host 的 skill 通道**,
   不得夾在工具回傳值裡繞過分類。

> **為什麼這條要寫進契約**:2026-08-15 實查 DeepSeek Harness 發現,
> 他們對跨 session 快照與排程提醒都有嚴謹的 untrusted framing
> (附禁令 + 把 `<` 逸出成 `\u003c` 讓來源文字拼不出標籤),
> **卻沒有把同一個分類套到本機 skill** —— 本機 skill 一旦落進 discovery root,
> 就被逐字當成 system 層指令。**「enabled」與「可以成為系統指令」是兩件事,
> 混在一起就是一條 prompt-injection 路徑。**

相關:Gmail 模組規格、
UI 鐵律拍板、
自我 trust 缺陷
