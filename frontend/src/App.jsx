import { useSelector } from 'react-redux'
import SearchBar from './components/SearchBar'
import ResultsList from './components/ResultsList'
import EnterpriseCard from './components/EnterpriseCard'

export default function App() {
  const selected = useSelector((s) => s.ui.selectedNumber)

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <span className="logo">🏨</span>
          <div>
            <strong>KBO Hôtellerie</strong>
            <small>Fiches financières</small>
          </div>
        </div>
        <SearchBar />
        <ResultsList />
      </aside>

      <main className="content">
        {selected ? (
          <EnterpriseCard number={selected} />
        ) : (
          <div className="empty">
            <span className="logo-lg">🏨</span>
            <h2>Recherchez une entreprise hôtelière</h2>
            <p className="muted">
              Par nom ou numéro BCE. Les fiches affichent l'identité (Silver), les ratios financiers
              consolidés (Gold), un Sankey du compte de résultat et les dirigeants (kbopub).
            </p>
          </div>
        )}
      </main>
    </div>
  )
}
