# MadCowork 架構說明

**版本：** madcowork-api（API Edition）  
**文件日期：** 2026-06-29  
**適用對象：** 產品、開發、部署與維運人員

---

## 1. 產品定位

MadCowork 是一套**桌面 AI 工作空間**（Agent Workspace）。使用者透過對話驅動 AI，讓它在受控權限下操作本機檔案、執行命令、搜尋網路、操作瀏覽器、排程任務，並完成簡報、醫療影像、工業檢測、郵件、HPC 等垂直工作流。

本專案為 **API Edition**：推論改由 OpenAI 相容的雲端 API 提供（例如 NCHC / RHAP），不需在本機安裝 Ollama。其餘 Agent 能力、工具、記憶與介面與本機版 MadCowork 相同。

| 版本 | 推論後端 | 適用場景 |
|------|----------|----------|
| MadCowork（本機版） | 本機 Ollama | 完全離線、不需 API key |
| madcowork-api（API 版） | 雲端 / 私有 OpenAI 相容 API | 相同 Agent 體驗，免本機模型部署 |

---

## 2. 技術棧

| 層級 | 技術 | 說明 |
|------|------|------|
| 桌面殼 | Electron 41 | 啟動後端、管理視窗、載入環境設定 |
| 前端 | React 19、TypeScript 6、Vite 8 | 對話介面、設定、Artifact 檢視 |
| 後端 | Node.js ≥ 22 | REST、WebSocket、工具執行、Agent 迴圈 |
| 關聯式資料 | better-sqlite3（SQLite WAL） | Session、對話串流、排程任務 |
| 向量記憶 | LanceDB | 跨 Session 語意召回 |
| 即時通訊 | WebSocket（ws） | 串流輸出、權限請求、控制訊息 |
| 外部協定 | MCP（Model Context Protocol） | 掛載第三方工具伺服器 |
| 領域腳本 | Python | DICOM、PLUX、郵件、HPC 等 |

---

## 3. 整體架構

系統分為三層：**桌面殼 → 後端服務 → 外部整合**。

```
┌─────────────────────────────────────────────────────────────┐
│                    使用者（桌面應用）                          │
├─────────────────────────────────────────────────────────────┤
│  Electron 主程序                                              │
│    · 載入 API key / 模型設定                                   │
│    · 啟動 Node 後端                                            │
│    · 開啟 React 渲染視窗                                       │
├─────────────────────────────────────────────────────────────┤
│  React 前端                                                   │
│    · 主面板：對話、側邊欄、啟動頁、設定                          │
│    · Agent 執行緒、Artifact、DICOM / PLUX 檢視器               │
│    · 指令面板、配對、主題與多語系                                │
├─────────────────────────────────────────────────────────────┤
│  Node 後端（預設 127.0.0.1:5180）                              │
│    · REST API：Session、設定、工作區                             │
│    · WebSocket：即時串流與權限互動                               │
│    · Worker：Agent 回合迴圈                                     │
│    · Tools：內建工具與 MCP 工具                                  │
│    · SQLite + LanceDB：持久化與記憶                              │
│    · Cron：排程任務                                             │
├─────────────────────────────────────────────────────────────┤
│  外部整合                                                     │
│    · LLM API（或本機 Ollama）                                  │
│    · Chrome 瀏覽器擴充（browser-mcp）                           │
│    · Python 腳本（DICOM / PLUX / Mail / HPC）                  │
│    · Skills 知識庫（Markdown 工作流手冊）                         │
│    · MCP 伺服器（Notion、GitHub、Slack 等）                     │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. 啟動與執行流程

### 4.1 應用啟動

1. Electron 主程序讀取環境設定（API key、Base URL、預設模型）。
2. 主程序以子程序方式啟動 Node 後端。
3. 後端完成初始化：資料庫、Worker、MCP 客戶端、排程器、Python 依賴檢查。
4. 後端在預設埠 **5180** 提供 HTTP 與 WebSocket 服務。
5. Electron 確認後端就緒後，開啟前端視窗並載入 React 介面。

### 4.2 單次對話（Agent Turn）

1. 使用者送出訊息，寫入 SQLite 的 stream_items。
2. Worker 偵測到新訊息，組出 LLM 可用的對話歷史。
3. 注入系統提示：專案記憶、跨 Session 向量召回、Skills 路由等。
4. 呼叫 LLM，附帶可用工具清單。
5. 若 LLM 要求呼叫工具：
   - 依 Session 的 permission_mode 決定是否需使用者點選核准。
   - 執行工具，將結果寫回對話串流。
   - 再次呼叫 LLM，形成工具迴圈（單輪最多約 16 次）。
6. 若 LLM 直接回覆文字，則結束本輪。
7. 背景寫入向量記憶，供未來 Session 召回。

### 4.3 權限模型

- **per-action（預設）**：每次寫檔、執行命令等敏感操作需使用者核准。
- **auto**：安全工具可自動執行。
- 使用者可對特定工具選擇「永遠允許」。
- 權限請求透過 WebSocket 即時推送至前端，逾時約 10 分鐘。

---

## 5. 後端核心模組

### 5.1 REST 路由

負責 Session 建立與刪除、對話項目讀寫、設定更新、工作區目錄操作、工具預設、裝置配對等。前端主要透過 REST 做 CRUD，透過 WebSocket 做即時更新。

### 5.2 WebSocket 串流

每個 Session 可訂閱專屬 WebSocket 通道。用途包括：

- 即時推送 Agent 回覆與工具輸出
- 權限請求與使用者回應（allow / deny）
- ask_user 互動（選項晶片）
- 中止進行中的回合（abort）

### 5.3 Agent Worker

系統心臟。持續監聽待處理的使用者訊息，驅動 LLM 與工具迴圈。具備：

- 防止同一訊息重複處理（記憶體鎖 + 資料庫檢查）
- 啟動時掃描遺留的未處理訊息
- 支援排程任務僅在 Session 閒置時觸發
- 自動產生 Session 標題

### 5.4 工具系統

內建約 20 種以上工具，分類如下：

| 類別 | 功能範圍 |
|------|----------|
| 檔案系統 | 讀寫檔案、列目錄、執行 Shell 命令 |
| 視覺與 PDF | 讀圖、OCR、PDF 文字與圖表擷取 |
| 網路 | 網頁搜尋、抓取網頁或 PDF |
| 簡報與報告 | 頁面模板、修訂、編輯 |
| 瀏覽器 | DOM 操作、點擊、輸入、截圖（需 Chrome 擴充） |
| Skills | 列出與讀取工作流手冊 |
| 排程 | 建立、刪除、列出 Cron 任務 |
| 編排 | 派生子 Agent、更新計畫 |

**工具白名單預設**（可在 Session 設定中選擇）：

- general：全部工具
- readonly：唯讀檔案與媒體
- research：唯讀 + 網路搜尋與 PDF
- paper2slides：簡報生成管線
- chromolab：色譜分析專用

### 5.5 資料持久化

**SQLite（關聯式）**

- Session 中繼資料（標題、權限模式、工作目錄、釘選狀態）
- stream_items：完整對話與工具呼叫紀錄
- scheduled_task：排程任務定義與下次執行時間
- 採 WAL 模式，支援向前相容的欄位遷移

**LanceDB（向量）**

- 每次 Agent 完成回覆後，將「使用者問題 + Agent 回答」向量化儲存
- 新 Session 開始時，依當前問題召回最相關的過往對話（預設 top-4）
- 召回結果自動注入系統提示，無需 Agent 主動呼叫
- API 版預設使用 bge-m3（1024 維）；本機版使用 nomic-embed-text（768 維）

**使用者設定**

- API key、模型選擇等存於使用者資料目錄的 settings.json
- 可在應用內 Settings 即時修改，無需重新打包

### 5.6 MCP 整合

- 設定檔預設位於使用者家目錄下的 .madcowork/mcp.json
- 後端啟動時以 stdio 連接各 MCP 伺服器
- 遠端工具以 mcp__伺服器名__工具名 格式暴露給 LLM
- 單一 MCP 伺服器故障不會導致整個後端崩潰

### 5.7 排程系統

- 支援使用者定義的 Cron 任務（定時向指定 Session 注入提示）
- 支援內部任務（如自動 dream 等）
- Session 忙碌時會延後執行，不會打斷進行中的對話

---

## 6. 前端架構

### 6.1 主要區塊

| 區塊 | 職責 |
|------|------|
| 啟動頁（Hero Launchpad） | 工作流卡片、選擇工作資料夾、快速開始 |
| 主面板（UnifiedPanel） | 側邊欄 Session 列表、Composer 輸入區 |
| Agent 執行緒 | 訊息串流、計畫卡、工具輸出、權限按鈕 |
| Artifact 面板 | 程式碼、文件、圖表等產出預覽 |
| 設定頁 | API key、模型、主題、音效、配對 |
| 專業檢視器 | DICOM 切片、PLUX 3D 表面、簡報預覽 |

### 6.2 使用者體驗要點

- 支援亮色 / 暗色主題，無載入閃爍
- API 版顯示「API MODE」橫幅，標示推論走雲端
- 快捷鍵：Command+K 指令面板、Command+N 新對話、Command+1–9 切換 Session
- 多步驟任務顯示內嵌計畫卡；完成時可播放提示音
- 支援跨裝置配對：另一台裝置可連至 executor 主機的 5180 埠

---

## 7. Skills 知識庫

Skills 是一組 Markdown 格式的工作流手冊，Agent 在需要時透過工具讀取並依步驟執行。相當於可版本化的「標準作業程序（SOP）」。

目前涵蓋領域包括：

| 領域 | 代表 Skills |
|------|-------------|
| HPC | 叢集登入、程式生成與 SFTP 上傳 |
| 郵件 | 多帳號搜尋、撰寫、標籤、規則管理 |
| 憑證設定 | 引導式 .env 設定、Excel 表單填寫 |
| 醫療影像 | DICOM CT/MR 系列檢視與分析 |
| 工業檢測 | PLUX 表面粗糙度、OK/NG 比對 |
| 簡報 | 論文轉簡報、資料轉投影片 |
| 整合設定 | Gmail、Slack、Line OA、Notion 等連接器 |
| 物件偵測 | YOLO 訓練與推論 |

部分設定意圖（如郵件帳號、HPC 帳號）會由後端**確定性路由**直接注入系統提示，無需 Agent 先搜尋 Skills。

---

## 8. 領域擴充（Python 腳本）

後端透過 exec_command 呼叫專用 Python 模組，處理 Node 不適合或已有成熟函式庫的領域：

| 模組 | 功能 |
|------|------|
| DICOM | CT/MR 切片檢視、度量、3D 等值面、偽彩色 |
| PLUX | Sensofar 表面讀取、粗糙度、OK/NG 比對、3D 檢視 |
| Mail | Gmail API、Outlook、mail2000、通用 IMAP |
| YOLO | 單張推論、訓練、評估、比對 |
| HPC | SSH 連線、SFTP 上傳、目錄列表、編輯器偏好 |

離線自包含建置可內建 portable Python 與預裝套件，目標主機無需另行安裝 Python 或 pip。

後端啟動時會依 DEPENDENCIES.md 自動檢查並安裝缺少的 pip 套件（非阻塞，失敗僅記錄警告）。

---

## 9. 瀏覽器橋接

browser-mcp 由兩部分組成：

1. **Chrome 擴充**：注入目標分頁，接收 DOM 操作指令
2. **Node WebSocket 橋接**：後端工具與擴充之間的中繼

啟用後，Agent 可對真實瀏覽器分頁執行點擊、輸入、截圖、等待元素等操作，適用於需登入或動態網頁的任務。

---

## 10. 工作區與安全邊界

### 10.1 工作區根目錄

- 每個 Session 可指定 work_dir（工作資料夾）
- 使用者可在啟動前或對話中變更工作區根目錄
- 資料夾選擇器支援自由導覽至檔案系統根目錄，並可當場建立新資料夾

### 10.2 安全機制

- 工具執行前進行路徑驗證，限制在允許範圍內
- 可設定封鎖目錄清單
- exec_command 對唯讀探測型 python -c 腳本有額外防護
- 敏感工具預設需 per-action 核准
- API key 存於使用者本機，權限 0600

---

## 11. API 版與本機版差異

| 項目 | 本機版（MadCowork） | API 版（madcowork-api） |
|------|---------------------|-------------------------|
| 推論 | 本機 Ollama | 雲端 OpenAI 相容 API |
| 預設模型 | gemma4:26b | 由 API 提供者決定（如 gemma-4-26B） |
| Embedding | nomic-embed-text | bge-m3 |
| 模型管理 UI | 載入 / 卸載 VRAM | API 模式標籤，無 VRAM 控制 |
| 離線能力 | 可完全離線（模型已下載時） | 需網路連至 API |
| 其餘能力 | 相同 | 相同 |

使用者可在 Settings → API keys → Model gateway 貼上自己的 key，並從下拉選單選擇該 key 可存取的模型，無需重新打包應用。

---

## 12. 部署與打包

### 12.1 開發模式

- 後端：獨立啟動 Node 後端（預設 5180）
- 前端：Vite 開發伺服器（預設 5179）
- 完整殼：Electron 開發模式同時啟動兩者

### 12.2 正式打包

- macOS：產生 .app 與 DMG，可進一步打包為 deploy.zip（含安裝腳本與 SHA256 校驗）
- Windows：NSIS 安裝程式，可用批次檔啟動
- Linux：AppImage

打包產物包含：前端 dist、Electron 主程序、後端程式、browser-mcp、Skills 庫、環境設定範本。離線建置可額外內建 runtime、models、assistant。

---

## 13. 典型使用情境

1. **研究與簡報**：讀取 PDF 論文或試算表，搜尋補充資料，產出投影片。
2. **檔案整理**：依規則重新命名、分類、批次處理資料夾。
3. **醫療影像**：開啟 DICOM 系列，檢視切片與 3D 重建。
4. **工業檢測**：讀取 PLUX 表面檔，計算粗糙度並判定 OK/NG。
5. **郵件自動化**：多帳號搜尋、回覆、標籤與規則管理。
6. **HPC 工作流**：登入叢集、生成排程腳本、本機編輯後 SFTP 上傳。
7. **網頁操作**：透過瀏覽器橋接完成需登入的網站任務。
8. **排程任務**：定時向 Agent 注入提示，執行重複性工作。

---

## 14. 架構設計原則（摘要）

1. **本機優先**：資料、Session、記憶預設存於使用者機器，減少雲端依賴（推論除外）。
2. **權限閘門**：敏感操作預設需人工核准，符合「Agent 可做事但不可失控」的產品定位。
3. **可擴充**：Skills、MCP、Python 腳本三條路徑擴充能力，不需改動核心 Worker。
4. **串流優先**：對話與工具輸出即時推送，而非等待整輪完成才顯示。
5. **容錯啟動**：MCP、Python 依賴、個別工具失敗不阻擋後端啟動。
6. **版本一致**：建置嵌入 Git SHA，便於跨裝置確認是否執行相同程式碼。

---

## 15. 一句話總結

**MadCowork 是以 Electron 為殼、React 為介面、Node 為 Agent 引擎的桌面 AI 工作空間**；透過 SQLite 持久化對話、LanceDB 實現跨 Session 記憶，並以內建工具、Skills 手冊、MCP 與 Python 腳本，讓 LLM 能在受控權限下完成檔案、網路、瀏覽器、排程與多種垂直領域任務。API 版僅將推論從本機 Ollama 替換為雲端 OpenAI 相容端點，其餘架構與能力保持一致。

---

*MadCowork / madcowork-api — IluvatarErua / artiwistech*
