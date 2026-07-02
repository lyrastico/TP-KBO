import { fmtEuro, fmtPct, fmtRatio } from '../format'

// Tableau des ratios financiers par exercice (une colonne par année).
export default function RatiosTable({ years }) {
  if (!years || years.length === 0) return <p className="muted">Aucun exercice disponible.</p>

  const rows = [
    { label: "Chiffre d'affaires", get: (y) => fmtEuro(y.ca) },
    { label: 'Marge brute', get: (y) => fmtEuro(y.marge_brute) },
    { label: 'EBIT (9901)', get: (y) => fmtEuro(y.ebit) },
    { label: 'Résultat net', get: (y) => fmtEuro(y.resultat_net) },
    { label: 'Fonds propres', get: (y) => fmtEuro(y.fonds_propres) },
    { label: 'Trésorerie', get: (y) => fmtEuro(y.tresorerie) },
    { label: 'Dettes financières', get: (y) => fmtEuro(y.dettes_financieres) },
    { label: 'Marge nette', get: (y) => fmtPct(y.ratios?.marge_nette_pct), strong: true },
    { label: 'ROE', get: (y) => fmtPct(y.ratios?.roe_pct), strong: true },
    { label: 'Ratio de liquidité', get: (y) => fmtRatio(y.ratios?.ratio_liquidite), strong: true },
    { label: "Taux d'endettement", get: (y) => fmtPct(y.ratios?.taux_endettement_pct), strong: true },
  ]

  return (
    <div className="table-scroll">
      <table className="ratios">
        <thead>
          <tr>
            <th>Poste</th>
            {years.map((y) => (
              <th key={y.year}>{y.year}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.label} className={row.strong ? 'ratio-strong' : ''}>
              <td className="row-label">{row.label}</td>
              {years.map((y) => (
                <td key={y.year}>{row.get(y)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
