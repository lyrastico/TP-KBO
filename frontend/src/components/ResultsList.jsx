import { useEffect, useState } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import { useSearchQuery } from '../api'
import { selectEnterprise } from '../uiSlice'

// Débounce simple pour ne pas requêter à chaque frappe.
function useDebounced(value, delay = 300) {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(id)
  }, [value, delay])
  return debounced
}

export default function ResultsList() {
  const dispatch = useDispatch()
  const query = useSelector((s) => s.ui.query)
  const selected = useSelector((s) => s.ui.selectedNumber)
  const debouncedQuery = useDebounced(query.trim())

  const { data, isFetching } = useSearchQuery(debouncedQuery, {
    skip: debouncedQuery.length < 2,
  })

  if (debouncedQuery.length < 2) {
    return <p className="muted pad">Saisissez au moins 2 caractères.</p>
  }

  return (
    <div className="results">
      {isFetching && <div className="spinner-row pad"><span className="spinner" /> Recherche…</div>}
      {data && data.results.length === 0 && <p className="muted pad">Aucun résultat.</p>}
      <ul>
        {data?.results.map((r) => (
          <li
            key={r.enterprise_number}
            className={r.enterprise_number === selected ? 'active' : ''}
            onClick={() => dispatch(selectEnterprise(r.enterprise_number))}
          >
            <div className="res-name">{r.name || '(sans nom)'}</div>
            <div className="res-meta">
              <span>{r.enterprise_number}</span>
              {r.city && <span>· {r.city}</span>}
              {r.has_financials && <span className="badge">comptes</span>}
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}
