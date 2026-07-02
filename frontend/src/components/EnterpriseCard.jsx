import { useEffect, useState } from 'react'
import { useEnterpriseQuery } from '../api'
import RatiosTable from './RatiosTable'
import Sankey from './Sankey'
import Directors from './Directors'

export default function EnterpriseCard({ number }) {
  const { data, isFetching, isError } = useEnterpriseQuery(number)
  const years = data?.gold?.years || []
  const [selectedYear, setSelectedYear] = useState(null)

  // À chaque changement d'entreprise, sélectionne l'exercice le plus récent.
  useEffect(() => {
    if (years.length) setSelectedYear(years[years.length - 1].year)
  }, [number, data]) // eslint-disable-line react-hooks/exhaustive-deps

  if (isFetching) return <div className="spinner-row pad"><span className="spinner" /> Chargement de la fiche…</div>
  if (isError || !data) return <p className="muted pad">Fiche indisponible.</p>

  const s = data.silver
  const addr = s.address
  const yearObj = years.find((y) => y.year === selectedYear)

  return (
    <div className="fiche">
      <header className="fiche-head">
        <h1>{s.name || '(sans nom)'}</h1>
        <div className="tags">
          <span className="tag">{s.JuridicalFormLabel}</span>
          <span className={`tag ${s.StatusLabel === 'Actif' ? 'ok' : ''}`}>{s.StatusLabel}</span>
          <span className="tag ghost">{number}</span>
        </div>
        {addr && (
          <p className="addr">
            {addr.StreetFR} {addr.HouseNumber}{addr.Box ? ` b${addr.Box}` : ''}, {addr.Zipcode} {addr.MunicipalityFR}
          </p>
        )}
      </header>

      <section className="card">
        <h3>Activités (NACE)</h3>
        <ul className="activities">
          {s.activities?.slice(0, 8).map((a, i) => (
            <li key={i}>
              <span className={`badge-nace ${a.Classification === 'MAIN' ? 'main' : ''}`}>{a.NaceCode}</span>
              {a.NaceLabel || '—'}
              {a.Classification === 'MAIN' && <span className="muted"> · principale</span>}
            </li>
          ))}
        </ul>
      </section>

      {data.gold ? (
        <>
          <section className="card">
            <div className="card-head">
              <h3>Compte de résultat (Sankey)</h3>
              <select value={selectedYear || ''} onChange={(e) => setSelectedYear(Number(e.target.value))}>
                {years.map((y) => (
                  <option key={y.year} value={y.year}>Exercice {y.year}</option>
                ))}
              </select>
            </div>
            <Sankey year={yearObj} />
          </section>

          <section className="card">
            <h3>Ratios financiers par année <span className="tag ghost">{data.gold.schema_type}</span></h3>
            <RatiosTable years={years} />
          </section>
        </>
      ) : (
        <section className="card">
          <p className="muted">Aucun compte annuel NBB pour cette entreprise (couche Gold vide).</p>
        </section>
      )}

      <Directors number={number} />
    </div>
  )
}
