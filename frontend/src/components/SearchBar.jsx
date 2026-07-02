import { useDispatch, useSelector } from 'react-redux'
import { setQuery } from '../uiSlice'

// Barre de recherche par nom ou numéro BCE. La requête est stockée dans Redux ;
// la liste de résultats réagit en temps réel (voir ResultsList).
export default function SearchBar() {
  const dispatch = useDispatch()
  const query = useSelector((s) => s.ui.query)

  return (
    <div className="searchbar">
      <input
        type="search"
        value={query}
        placeholder="Rechercher un hôtel par nom ou numéro BCE…"
        onChange={(e) => dispatch(setQuery(e.target.value))}
        autoFocus
      />
    </div>
  )
}
