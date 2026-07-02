import { useLazyDirectorsQuery } from '../api'

// Dirigeants scrapés à la demande depuis kbopub (une fois, puis persistés côté API).
// Un spinner s'affiche pendant la récupération, comme pour le streaming SSE.
export default function Directors({ number }) {
  const [trigger, { data, isFetching, isError }] = useLazyDirectorsQuery()

  return (
    <section className="card">
      <div className="card-head">
        <h3>Dirigeants et représentants</h3>
        {!data && !isFetching && (
          <button className="btn" onClick={() => trigger(number)}>
            Charger depuis kbopub
          </button>
        )}
      </div>

      {isFetching && <div className="spinner-row"><span className="spinner" /> Scraping kbopub…</div>}
      {isError && <p className="muted">Impossible de récupérer les dirigeants (kbopub injoignable).</p>}

      {data && (
        data.directors.length === 0 ? (
          <p className="muted">Aucune fonction publiée pour cette entreprise.</p>
        ) : (
          <ul className="directors">
            {data.directors.map((d, i) => (
              <li key={i}>
                <span className="dir-fn">{d.function}</span>
                <span className="dir-name">{d.name}</span>
                <span className="dir-since">{d.since}</span>
              </li>
            ))}
          </ul>
        )
      )}
    </section>
  )
}
