import { fmtEuro } from '../format'

// Sankey du compte de résultat, 3 nœuds fixes (énoncé) :
//   Chiffre d'affaires (70)  ->  Marge brute (70 - 60 + 71)  ->  Résultat net (9904)
// Les rubans entre nœuds sont dimensionnés par la valeur aval ; l'écart amont-aval
// est représenté comme une « fuite » de charges (gris), et une perte éventuelle en
// rouge. Quand le CA n'est pas publié (petits schémas), le flux part de la marge brute.

const W = 720
const H = 320
const PAD = 44
const NODE_W = 26
const GAP_LABEL = 22

function Ribbon({ x1, x2, y1a, y1b, y2a, y2b, color, opacity = 0.5 }) {
  // Bézier horizontale reliant [y1a,y1b] (gauche) à [y2a,y2b] (droite).
  const mx = (x1 + x2) / 2
  const d = [
    `M ${x1} ${y1a}`,
    `C ${mx} ${y1a}, ${mx} ${y2a}, ${x2} ${y2a}`,
    `L ${x2} ${y2b}`,
    `C ${mx} ${y2b}, ${mx} ${y1b}, ${x1} ${y1b}`,
    'Z',
  ].join(' ')
  return <path d={d} fill={color} opacity={opacity} />
}

export default function Sankey({ year }) {
  if (!year) return null
  const ca = year.ca
  const marge = year.marge_brute
  const net = year.resultat_net

  // Échelle : plus grande valeur positive parmi les postes présents.
  const base = Math.max(ca || 0, marge || 0, Math.abs(net || 0), 1)
  const scale = (v) => (Math.abs(v || 0) / base) * (H - 2 * PAD)

  // Colonnes des 3 nœuds.
  const nodes = []
  if (ca != null) nodes.push({ key: 'ca', label: "Chiffre d'affaires", value: ca, color: '#2563eb' })
  if (marge != null) nodes.push({ key: 'mb', label: 'Marge brute', value: marge, color: '#0d9488' })
  if (net != null)
    nodes.push({ key: 'rn', label: 'Résultat net', value: net, color: net >= 0 ? '#16a34a' : '#dc2626' })

  if (nodes.length < 2) {
    return <p className="muted">Données insuffisantes pour le Sankey de cet exercice.</p>
  }

  const colGap = (W - 2 * PAD - NODE_W) / (nodes.length - 1)
  const layout = nodes.map((n, i) => {
    const h = Math.max(scale(n.value), 3)
    const x = PAD + i * colGap
    const yTop = PAD + ((H - 2 * PAD) - h) / 2
    return { ...n, x, h, yTop, yBot: yTop + h }
  })

  const leaks = [] // charges « sortantes » entre deux nœuds
  const ribbons = []
  for (let i = 0; i < layout.length - 1; i++) {
    const a = layout[i]
    const b = layout[i + 1]
    const kept = Math.max(b.value, 0)
    const keptH = Math.max(scale(kept), 0)
    // Ruban conservé (du haut du nœud amont vers le nœud aval).
    ribbons.push(
      <Ribbon
        key={`r${i}`}
        x1={a.x + NODE_W}
        x2={b.x}
        y1a={a.yTop}
        y1b={a.yTop + keptH}
        y2a={b.yTop}
        y2b={b.yTop + Math.max(scale(b.value >= 0 ? b.value : 0), 0)}
        color={b.color}
        opacity={0.45}
      />,
    )
    // Fuite = charges consommées entre les deux postes (gris), ou perte (rouge).
    const lost = a.value - b.value
    if (lost > 0) {
      const lostH = scale(lost)
      const label = i === 0 ? 'Achats & consommations' : 'Autres charges'
      leaks.push({ x: (a.x + NODE_W + b.x) / 2, y: a.yTop + keptH + lostH / 2, label, value: lost, color: '#94a3b8' })
    }
    if (b.value < 0) {
      leaks.push({ x: b.x + NODE_W / 2, y: b.yBot + 16, label: 'Perte', value: b.value, color: '#dc2626' })
    }
  }

  return (
    <div className="sankey">
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Sankey compte de résultat">
        {ribbons}
        {layout.map((n) => (
          <g key={n.key}>
            <rect x={n.x} y={n.yTop} width={NODE_W} height={n.h} rx="4" fill={n.color} />
            <text x={n.x + NODE_W / 2} y={n.yTop - GAP_LABEL + 8} textAnchor="middle" className="sankey-label">
              {n.label}
            </text>
            <text x={n.x + NODE_W / 2} y={n.yBot + 16} textAnchor="middle" className="sankey-value">
              {fmtEuro(n.value)}
            </text>
          </g>
        ))}
        {leaks.map((l, i) => (
          <text key={i} x={l.x} y={l.y} textAnchor="middle" className="sankey-leak" fill={l.color}>
            {l.label} · {fmtEuro(l.value)}
          </text>
        ))}
      </svg>
    </div>
  )
}
