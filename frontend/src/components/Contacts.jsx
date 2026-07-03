// Informations de contact issues de la couche Silver (KBO Open Data, table contact).
// Trois types possibles : EMAIL, WEB, TEL. Rien à scraper : déjà dans la fiche.

const META = {
  EMAIL: { label: 'E-mail', icon: '✉', href: (v) => `mailto:${v}` },
  WEB: { label: 'Site web', icon: '🌐', href: (v) => (/^https?:/.test(v) ? v : `http://${v}`) },
  TEL: { label: 'Téléphone', icon: '☎', href: (v) => `tel:${v.replace(/\s/g, '')}` },
}

export default function Contacts({ contacts }) {
  if (!contacts || contacts.length === 0) return null

  return (
    <section className="card">
      <h3>Informations de contact</h3>
      <ul className="contacts">
        {contacts.map((c, i) => {
          const meta = META[c.ContactType] || { label: c.ContactType, icon: '•', href: () => null }
          const href = meta.href(c.Value)
          return (
            <li key={i}>
              <span className="contact-ico" aria-hidden>{meta.icon}</span>
              <span className="contact-type">{meta.label}</span>
              {href ? (
                <a href={href} target="_blank" rel="noreferrer">{c.Value}</a>
              ) : (
                <span>{c.Value}</span>
              )}
            </li>
          )
        })}
      </ul>
    </section>
  )
}
