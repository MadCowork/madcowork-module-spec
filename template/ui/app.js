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
refresh()
