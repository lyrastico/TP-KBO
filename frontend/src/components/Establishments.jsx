// Unités d'établissement (KBO Open Data, table establishment) : numéro + date de début.
// Lien vers la fiche publique kbopub de chaque unité pour le détail (adresse, activités).

function kbopubUnit(number) {
  const digits = number.replace(/\D/g, '')
  return `https://kbopub.economie.fgov.be/kbopub/vestiginglijst.html?ondernemingsnummer=${digits}`
}

export default function Establishments({ establishments }) {
  if (!establishments || establishments.length === 0) return null

  const sorted = [...establishments].sort((a, b) =>
    (a.StartDate || '').localeCompare(b.StartDate || ''),
  )

  return (
    <section className="card">
      <h3>
        Établissements <span className="tag ghost">{establishments.length}</span>
      </h3>
      <ul className="establishments">
        {sorted.map((e, i) => (
          <li key={i}>
            <a href={kbopubUnit(e.EstablishmentNumber)} target="_blank" rel="noreferrer" className="etab-num">
              {e.EstablishmentNumber}
            </a>
            <span className="etab-date muted">
              {e.StartDate ? `depuis le ${e.StartDate}` : '—'}
            </span>
          </li>
        ))}
      </ul>
    </section>
  )
}
