const euro = new Intl.NumberFormat('fr-FR', {
  style: 'currency',
  currency: 'EUR',
  maximumFractionDigits: 0,
})

export function fmtEuro(value) {
  if (value === null || value === undefined) return '—'
  return euro.format(value)
}

export function fmtPct(value) {
  if (value === null || value === undefined) return '—'
  return `${value.toFixed(1)} %`
}

export function fmtRatio(value) {
  if (value === null || value === undefined) return '—'
  return value.toFixed(2)
}
