const BEIJING_TIME_ZONE = 'Asia/Shanghai'

function pad(value, size = 2) {
  return String(value).padStart(size, '0')
}

function parseNaiveBeijingString(value) {
  const match = String(value || '')
    .trim()
    .replace(' ', 'T')
    .replace(/\.(\d{3})\d+$/, '.$1')
    .match(/^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2})(?::(\d{2})(?::(\d{2})(?:\.(\d{1,3}))?)?)?)?$/)
  if (!match) return null
  const [, year, month, day, hour = '00', minute = '00', second = '00', millisecond = '0'] = match
  return new Date(
    Date.UTC(
      Number(year),
      Number(month) - 1,
      Number(day),
      Number(hour) - 8,
      Number(minute),
      Number(second),
      Number(pad(millisecond, 3))
    )
  )
}

export function parseBeijingDate(value) {
  if (value === null || value === undefined || value === '') return null
  if (value instanceof Date) return new Date(value.getTime())
  if (typeof value === 'number') {
    const timestamp = String(value).length === 10 ? value * 1000 : value
    const date = new Date(timestamp)
    return Number.isNaN(date.getTime()) ? null : date
  }
  const raw = String(value).trim()
  if (!raw) return null
  if (/^\d+$/.test(raw)) {
    return parseBeijingDate(Number(raw))
  }
  if (/[zZ]$|[+-]\d{2}:\d{2}$/.test(raw)) {
    const date = new Date(raw)
    return Number.isNaN(date.getTime()) ? null : date
  }
  const naiveDate = parseNaiveBeijingString(raw)
  if (naiveDate) return naiveDate
  const fallbackDate = new Date(raw.replace(/-/g, '/'))
  return Number.isNaN(fallbackDate.getTime()) ? null : fallbackDate
}

export function getBeijingDateParts(value) {
  const date = parseBeijingDate(value)
  if (!date) return null
  const formatter = new Intl.DateTimeFormat('zh-CN-u-ca-gregory', {
    timeZone: BEIJING_TIME_ZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
    weekday: 'short',
  })
  const parts = {}
  formatter.formatToParts(date).forEach((item) => {
    if (item.type !== 'literal') {
      parts[item.type] = item.value
    }
  })
  const weekMap = { 周日: '日', 周一: '一', 周二: '二', 周三: '三', 周四: '四', 周五: '五', 周六: '六' }
  return {
    y: parts.year,
    m: parts.month,
    d: parts.day,
    h: parts.hour,
    i: parts.minute,
    s: parts.second,
    a: weekMap[parts.weekday] || parts.weekday || '',
  }
}

export function formatBeijingDateTime(value, options = {}) {
  const { fallback = '待补充', withTime = true, withSeconds = false } = options
  const parts = getBeijingDateParts(value)
  if (!parts) return fallback
  const datePart = `${parts.y}-${parts.m}-${parts.d}`
  if (!withTime) return datePart
  const timePart = withSeconds ? `${parts.h}:${parts.i}:${parts.s}` : `${parts.h}:${parts.i}`
  return `${datePart} ${timePart}`
}
