// Comptes annuels déposés à la BNB (couche Gold). Un exercice = un dépôt exploité,
// avec sa référence NBB, son schéma (full/abrégé/micro) et son code modèle.

const SCHEMA_LABEL = { full: 'Complet', abrege: 'Abrégé', micro: 'Micro' }

export default function AnnualAccounts({ number, years }) {
  if (!years || years.length === 0) return null

  const digits = (number || '').replace(/\D/g, '')
  const bnb = `https://consult.cbso.nbb.be/consult-enterprise/${digits}`
  const desc = [...years].sort((a, b) => b.year - a.year)

  return (
    <section className="card">
      <div className="card-head">
        <h3>Comptes annuels déposés (NBB)</h3>
        <a className="btn ghost" href={bnb} target="_blank" rel="noreferrer">
          Consulter à la BNB ↗
        </a>
      </div>
      <div className="table-scroll">
        <table className="accounts">
          <thead>
            <tr>
              <th>Exercice</th>
              <th>Schéma</th>
              <th>Code modèle</th>
              <th>Référence NBB</th>
            </tr>
          </thead>
          <tbody>
            {desc.map((y) => (
              <tr key={y.year}>
                <td className="row-label">{y.year}</td>
                <td>{SCHEMA_LABEL[y.schema_type] || y.schema_type}</td>
                <td>{y.model_code || '—'}</td>
                <td className="muted">{y.reference || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
