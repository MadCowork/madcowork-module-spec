// Nine languages are required, not a bonus. The host tells you which one the
// user picked — do not guess from the browser.
export const LANGS = ['zh','en','ja','ko','fr','es','pt','de','it']
const en = { title:'Notes', loading:'Loading…', newNote:'New note', save:'Save',
  stored:'Stored', saved:'Saved note #{id}', empty:'No notes yet', failed:'Could not reach the module',
  agentCard:'From MadCowork', agentDismiss:'Dismiss' }
const dict = {
  en,
  zh:{title:'筆記',loading:'載入中…',newNote:'新增筆記',save:'儲存',stored:'已儲存',saved:'已儲存 #{id}',empty:'還沒有筆記',failed:'連不上模組',agentCard:'來自 MadCowork',agentDismiss:'關閉'},
  ja:{title:'メモ',loading:'読み込み中…',newNote:'新しいメモ',save:'保存',stored:'保存済み',saved:'メモ #{id} を保存',empty:'メモはまだありません',failed:'モジュールに接続できません',agentCard:'MadCowork より',agentDismiss:'閉じる'},
  ko:{title:'메모',loading:'불러오는 중…',newNote:'새 메모',save:'저장',stored:'저장됨',saved:'메모 #{id} 저장됨',empty:'메모가 없습니다',failed:'모듈에 연결할 수 없습니다',agentCard:'MadCowork에서',agentDismiss:'닫기'},
  fr:{title:'Notes',loading:'Chargement…',newNote:'Nouvelle note',save:'Enregistrer',stored:'Enregistrées',saved:'Note #{id} enregistrée',empty:'Aucune note',failed:'Module injoignable',agentCard:'De MadCowork',agentDismiss:'Fermer'},
  es:{title:'Notas',loading:'Cargando…',newNote:'Nueva nota',save:'Guardar',stored:'Guardadas',saved:'Nota #{id} guardada',empty:'Sin notas',failed:'No se puede conectar con el módulo',agentCard:'De MadCowork',agentDismiss:'Cerrar'},
  pt:{title:'Notas',loading:'A carregar…',newNote:'Nova nota',save:'Guardar',stored:'Guardadas',saved:'Nota #{id} guardada',empty:'Sem notas',failed:'Módulo inacessível',agentCard:'De MadCowork',agentDismiss:'Fechar'},
  de:{title:'Notizen',loading:'Wird geladen…',newNote:'Neue Notiz',save:'Speichern',stored:'Gespeichert',saved:'Notiz #{id} gespeichert',empty:'Noch keine Notizen',failed:'Modul nicht erreichbar',agentCard:'Von MadCowork',agentDismiss:'Schließen'},
  it:{title:'Note',loading:'Caricamento…',newNote:'Nuova nota',save:'Salva',stored:'Salvate',saved:'Nota #{id} salvata',empty:'Nessuna nota',failed:'Modulo non raggiungibile',agentCard:'Da MadCowork',agentDismiss:'Chiudi'},
}
export const pickLang = v => LANGS.includes(String(v||'').toLowerCase()) ? String(v).toLowerCase() : 'en'
export const makeT = lang => (key, vars = {}) => {
  let value = (dict[lang] || en)[key] ?? en[key] ?? key
  for (const [k, v] of Object.entries(vars)) value = value.replaceAll(`{${k}}`, String(v))
  return value
}
