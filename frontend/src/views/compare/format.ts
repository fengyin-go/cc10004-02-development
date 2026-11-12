/** 展示用格式化：空字符串、null 与数字 0 必须肉眼可分辨。 */

export function displayRaw(value: unknown): string {
  if (value === undefined) return '—'
  if (value === null) return '空值 (null)'
  if (typeof value === 'string') {
    if (value === '') return '空字符串 ("")'
    if (value.trim() === '') return `空白字符串 ("${value}")`
    return value
  }
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  return String(value)
}

export function displayKind(kind: string): string {
  switch (kind) {
    case 'null':
      return '空值 null'
    case 'blank':
      return '空字符串'
    case 'missing':
      return '缺行'
    case 'number':
      return '数值'
    default:
      return '文本'
  }
}

export function shortDigest(digest: string | null | undefined): string {
  if (!digest) return '—'
  return digest.slice(0, 12)
}

export function formatTime(value: string | null | undefined): string {
  if (!value) return '—'
  return value.replace('T', ' ')
}

export function rowStateLabel(state: string): string {
  switch (state) {
    case 'paired':
      return '已配对'
    case 'missing_base':
      return '基准缺行'
    case 'missing_control':
      return '对照缺行'
    default:
      return state
  }
}

export function statusTone(status: string): string {
  switch (status) {
    case '计算中':
      return 'tone-info'
    case '计算完成':
      return 'tone-ok'
    case '已阻断':
      return 'tone-danger'
    case '已签认':
      return 'tone-signed'
    default:
      return 'tone-muted'
  }
}

export const CELL_STATUS_LABELS: Record<string, string> = {
  diff: '数值差（超阈值）',
  within: '阈值内 / 一致',
  missing: '缺行',
  null: '空值',
}
