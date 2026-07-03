import { useLazyLinksQuery } from '../api'

// Liens entre entités (scrapés kbopub, persistés) + liens externes officiels
// (documents juridiques, publications, registres — URLs déterministes).
// Chargés à la demande, comme les dirigeants (un seul fetch backend pour les deux).

const CATEGORIES = [
  { key: 'documents', title: 'Documents juridiques' },
  { key: 'publications', title: 'Publications' },
  { key: 'registres', title: 'Autres registres' },
]

function ExternalLinks({ links }) {
  if (!links || links.length === 0) return null
  return (
    <div className="ext-groups">
      {CATEGORIES.map((cat) => {
        const items = links.filter((l) => l.category === cat.key)
        if (items.length === 0) return null
        return (
          <div key={cat.key} className="ext-group">
            <h4>{cat.title}</h4>
            <ul className="ext-links">
              {items.map((l, i) => (
                <li key={i}>
                  <a href={l.url} target="_blank" rel="noreferrer">{l.label} ↗</a>
                </li>
              ))}
            </ul>
          </div>
        )
      })}
    </div>
  )
}

function kbopubEnterprise(number) {
  const digits = number.replace(/\D/g, '')
  return `https://kbopub.economie.fgov.be/kbopub/toonondernemingps.html?lang=fr&ondernemingsnummer=${digits}`
}

function EntityLinks({ links, onSelect }) {
  if (!links || links.length === 0) {
    return <p className="muted">Aucun lien entre entités publié.</p>
  }
  return (
    <ul className="entity-links">
      {links.map((l, i) => (
        <li key={i}>
          {l.in_db ? (
            <button className="link-num" onClick={() => onSelect?.(l.number)} title="Ouvrir la fiche">
              {l.number}
            </button>
          ) : (
            <a
              className="link-num ext"
              href={kbopubEnterprise(l.number)}
              target="_blank"
              rel="noreferrer"
              title="Entité radiée / absente de la base — consulter sur kbopub"
            >
              {l.number} ↗
            </a>
          )}
          {l.name && <span className="link-name">{l.name}</span>}
          <span className="link-rel muted">{l.relation}{l.since ? ` · depuis le ${l.since}` : ''}</span>
        </li>
      ))}
    </ul>
  )
}

export default function Links({ number, onSelect }) {
  const [trigger, { data, isFetching, isError }] = useLazyLinksQuery()

  return (
    <section className="card">
      <div className="card-head">
        <h3>Liens entre entités & documents officiels</h3>
        {!data && !isFetching && (
          <button className="btn" onClick={() => trigger(number)}>
            Charger depuis kbopub
          </button>
        )}
      </div>

      {isFetching && <div className="spinner-row"><span className="spinner" /> Scraping kbopub…</div>}
      {isError && <p className="muted">Impossible de récupérer les liens (kbopub injoignable).</p>}

      {data && (
        <>
          <EntityLinks links={data.entity_links} onSelect={onSelect} />
          <ExternalLinks links={data.external_links} />
        </>
      )}
    </section>
  )
}
