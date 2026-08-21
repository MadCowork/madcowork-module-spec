// Nine languages are required, not a bonus. The host tells you which one the
// user picked — do not guess from the browser.
export const LANGS = ['zh','en','ja','ko','fr','es','pt','de','it']
const en = { title:'Notes', loading:'Loading…', newNote:'New note', save:'Save',
  stored:'Stored', saved:'Saved note #{id}', empty:'No notes yet', failed:'Could not reach the module' }
const dict = {
  en,
  zh:{title:'筆記',loading:'載入中…',newNote:'新增筆記',save:'儲存',stored:'已儲存',saved:'已儲存 #{id}',empty:'還沒有筆記',failed:'連不上模組'},
  ja:{title:'メモ',loading:'読み込み中…',newNote:'新しいメモ',save:'保存',stored:'保存済み',saved:'メモ #{id} を保存',empty:'メモはまだありません',failed:'モジュールに接続できません'},
  ko:{title:'메모',loading:'불러오는 중…',newNote:'새 메모',save:'저장',stored:'저장됨',saved:'메모 #{id} 저장됨',empty:'메모가 없습니다',failed:'모듈에 연결할 수 없습니다'},
  fr:{title:'Notes',loading:'Chargement…',newNote:'Nouvelle note',save:'Enregistrer',stored:'Enregistrées',saved:'Note #{id} enregistrée',empty:'Aucune note',failed:'Module injoignable'},
  es:{title:'Notas',loading:'Cargando…',newNote:'Nueva nota',save:'Guardar',stored:'Guardadas',saved:'Nota #{id} guardada',empty:'Sin notas',failed:'No se puede conectar con el módulo'},
  pt:{title:'Notas',loading:'A carregar…',newNote:'Nova nota',save:'Guardar',stored:'Guardadas',saved:'Nota #{id} guardada',empty:'Sem notas',failed:'Módulo inacessível'},
  de:{title:'Notizen',loading:'Wird geladen…',newNote:'Neue Notiz',save:'Speichern',stored:'Gespeichert',saved:'Notiz #{id} gespeichert',empty:'Noch keine Notizen',failed:'Modul nicht erreichbar'},
  it:{title:'Note',loading:'Caricamento…',newNote:'Nuova nota',save:'Salva',stored:'Salvate',saved:'Nota #{id} salvata',empty:'Nessuna nota',failed:'Modulo non raggiungibile'},
}
export const pickLang = v => LANGS.includes(String(v||'').toLowerCase()) ? String(v).toLowerCase() : 'en'
export const makeT = lang => (key, vars = {}) => {
  let value = (dict[lang] || en)[key] ?? en[key] ?? key
  for (const [k, v] of Object.entries(vars)) value = value.replaceAll(`{${k}}`, String(v))
  return value
}
