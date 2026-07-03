import { fmtEuro } from '../format'

// Évolution du chiffre d'affaires (70) et du résultat net (9904) par exercice.
// Barres groupées sur une échelle € commune signée : le résultat net (bien plus
// petit que le CA, parfois négatif) se lit relativement au CA, et une perte
// descend sous la ligne du zéro. Couvre tous les exercices présents en Gold
// (2021→2025, ou depuis la création si l'historique remonte plus haut).

const H = 300
const PAD_T = 24
const PAD_B = 40
const PAD_L = 64
const PAD_R = 16

function niceCeil(v) {
  if (v <= 0) return 0
  const mag = Math.pow(10, Math.floor(Math.log10(v)))
  return Math.ceil(v / mag) * mag
}

export default function RevenueChart({ years }) {
  const data = (years || []).filter((y) => y.ca != null || y.resultat_net != null)
  if (data.length === 0) {
    return <p className="muted">Aucune donnée de chiffre d'affaires ou de résultat net.</p>
  }

  const W = Math.max(360, 90 * data.length + PAD_L + PAD_R)
  const maxPos = niceCeil(Math.max(...data.map((y) => Math.max(y.ca || 0, y.resultat_net || 0, 0)), 1))
  const minNeg = Math.min(...data.map((y) => Math.min(y.resultat_net || 0, 0)))
  const minVal = minNeg < 0 ? -niceCeil(-minNeg) : 0
  const range = maxPos - minVal || 1

  const plotH = H - PAD_T - PAD_B
  const y0 = PAD_T + ((maxPos - 0) / range) * plotH // pixel de la ligne zéro
  const scaleH = (v) => (Math.abs(v) / range) * plotH
  const bandW = (W - PAD_L - PAD_R) / data.length
  const barW = Math.min(30, bandW * 0.32)

  const bar = (v, cx, color) => {
    if (v == null) return null
    const h = scaleH(v)
    const y = v >= 0 ? y0 - h : y0
    return <rect x={cx - barW / 2} y={y} width={barW} height={Math.max(h, 1)} rx="3" fill={color} />
  }

  // Graduations horizontales (0, max, et min si négatif).
  const ticks = [0, maxPos, ...(minVal < 0 ? [minVal] : [])]

  return (
    <div className="revchart">
      <div className="legend">
        <span><i className="sw" style={{ background: '#2563eb' }} /> Chiffre d'affaires</span>
        <span><i className="sw" style={{ background: '#16a34a' }} /> Résultat net (＋)</span>
        <span><i className="sw" style={{ background: '#dc2626' }} /> Résultat net (−)</span>
      </div>
      <div className="table-scroll">
        <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Chiffre d'affaires et résultat net par exercice">
          {ticks.map((t, i) => {
            const y = PAD_T + ((maxPos - t) / range) * plotH
            return (
              <g key={i}>
                <line x1={PAD_L} x2={W - PAD_R} y1={y} y2={y} stroke={t === 0 ? '#94a3b8' : '#e5e7eb'} />
                <text x={PAD_L - 8} y={y + 4} textAnchor="end" className="chart-tick">{fmtEuro(t)}</text>
              </g>
            )
          })}
          {data.map((y, i) => {
            const cx = PAD_L + bandW * (i + 0.5)
            const rnColor = (y.resultat_net || 0) >= 0 ? '#16a34a' : '#dc2626'
            return (
              <g key={y.year}>
                {bar(y.ca, cx - barW * 0.58, '#2563eb')}
                {bar(y.resultat_net, cx + barW * 0.58, rnColor)}
                <text x={cx} y={H - PAD_B + 20} textAnchor="middle" className="chart-year">{y.year}</text>
              </g>
            )
          })}
        </svg>
      </div>
    </div>
  )
}
