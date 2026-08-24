// Writes go through POST /api/action with the module token. The token arrives in
// the URL when MadCowork opens this page and is never stored.
import { makeT, pickLang } from './i18n.js'
const params = new URLSearchParams(location.search)
const token = params.get('token') || ''
const t = makeT(pickLang(params.get('lang')))
document.documentElement.lang = pickLang(params.get('lang'))
const $ = id => document.getElementById(id)
for (const el of document.querySelectorAll('[data-i18n]')) el.textContent = t(el.dataset.i18n)

const call = async (action, args = {}) => {
  const res = await fetch('/api/action', { method:'POST',
    headers:{'Content-Type':'application/json','X-MadCowork-Module-Token':token},
    body: JSON.stringify({ action, args }) })
  const data = await res.json().catch(() => ({ ok:false, error:`HTTP ${res.status}` }))
  if (!res.ok || !data.ok) throw new Error(data.error || `HTTP ${res.status}`)
  return data.result
}
const say = (text, isError = false) => { $('msg').textContent = text; $('msg').className = isError ? 'msg err' : 'msg' }

async function refresh() {
  try {
    const { notes } = await call('list_notes')
    $('notes').replaceChildren()
    if (!notes.length) {
      const d = document.createElement('div'); d.className = 'empty'; d.textContent = t('empty')
      $('notes').append(d)
    }
    for (const n of notes) {
      const li = document.createElement('li'); li.className = 'item'
      const b = document.createElement('div'); b.textContent = n.body
      const m = document.createElement('div'); m.className = 'm'; m.textContent = `#${n.id} · ${n.created_at}`
      li.append(b, m); $('notes').append(li)
    }
    $('status').textContent = `${notes.length}`
  } catch (e) { $('status').textContent = t('failed'); say(e.message, true) }
}
$('save').onclick = async () => {
  $('save').disabled = true
  try { const r = await call('add_note', { body: $('body').value }); $('body').value = ''; say(t('saved', { id: r.note_id })); await refresh() }
  catch (e) { say(e.message, true) } finally { $('save').disabled = false }
}

// ── 面板通道的消費端(§11b)────────────────────────────────────────────────
//
// 這一半是參考實作,不是裝飾。後端 `_panel.py` 幫你擋掉了保留鍵與長度,
// **但它不做逃逸** —— 卡片的標題與內文出自模型,對這個頁面而言是外部輸入。
// 所以這裡一律 createElement + textContent,不碰 innerHTML:
// 用 innerHTML 拼字串時,漏一個 escape 就等於把頁面交給模型的輸出。
// createElement 這條路沒有「漏一個」這種可能。
//
// 三件事這個實作在示範:
//   1. 卡片有自己的容器、自己的樣式、每張都標來源 —— 模型的判讀不得無標記地
//      混在模組查出來的事實旁邊。
//   2. focus 是模型的請求,不是命令 —— 這裡照做,但頁面自己決定怎麼呈現。
//   3. 回報 state 給模型,讓它知道使用者正在看什麼(這是「on agent」的另一半:
//      沒有回報,模型只能盲目下指令)。
let panelSeq = -1

function renderAgentCards(cards) {
  const host = $('agentCards')
  host.replaceChildren()
  for (const card of cards) {
    const box = document.createElement('div')
    box.className = `agent-card ${card.level === 'warn' ? 'warn' : ''}`.trim()
    const head = document.createElement('div'); head.className = 'ac-head'
    const src = document.createElement('span'); src.className = 'ac-src'; src.textContent = t('agentCard')
    const title = document.createElement('span'); title.className = 'ac-title'; title.textContent = card.title ?? ''
    const close = document.createElement('button'); close.className = 'ac-close'; close.textContent = t('agentDismiss')
    close.onclick = async () => { try { await call('panel_dismiss') } catch {} renderAgentCards([]) }
    head.append(src, title, close)
    box.append(head)
    for (const line of card.lines || []) {
      const p = document.createElement('p'); p.textContent = line; box.append(p)
    }
    host.append(box)
  }
  host.hidden = cards.length === 0
}

async function panelTick() {
  let payload
  // 連不上就安靜跳過:面板通道是加值,不該讓輪詢失敗蓋掉使用者正在做的事。
  try { payload = await call('panel_pull', { state: { notes: $('status').textContent } }) } catch { return }
  if (payload.seq !== panelSeq) { panelSeq = payload.seq; renderAgentCards(payload.cards || []) }
}
setInterval(panelTick, 2000)

refresh()
