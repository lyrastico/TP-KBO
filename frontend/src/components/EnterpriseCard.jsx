import { useEffect, useState } from 'react'
import { useDispatch } from 'react-redux'
import { useEnterpriseQuery } from '../api'
import { selectEnterprise } from '../uiSlice'
import RatiosTable from './RatiosTable'
import RevenueChart from './RevenueChart'
import Sankey from './Sankey'
import Directors from './Directors'
import Contacts from './Contacts'
import Establishments from './Establishments'
import AnnualAccounts from './AnnualAccounts'
import Links from './Links'

export default function EnterpriseCard({ number }) {
  const dispatch = useDispatch()
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
          {s.StartDate && <span className="tag ghost">créée le {s.StartDate}</span>}
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

      <Contacts contacts={s.contacts} />

      {data.gold ? (
        <>
          <section className="card">
            <h3>Chiffre d'affaires & résultat net</h3>
            <RevenueChart years={years} />
          </section>

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

          <AnnualAccounts number={number} years={years} />
        </>
      ) : (
        <section className="card">
          <p className="muted">Aucun compte annuel NBB pour cette entreprise (couche Gold vide).</p>
        </section>
      )}

      <Establishments establishments={s.establishments} />

      <Links number={number} onSelect={(n) => dispatch(selectEnterprise(n))} />

      <Directors number={number} />
    </div>
  )
}
