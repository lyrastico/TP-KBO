import { createSlice } from '@reduxjs/toolkit'

// État d'interface : entreprise sélectionnée + requête de recherche courante.
const uiSlice = createSlice({
  name: 'ui',
  initialState: { selectedNumber: null, query: '' },
  reducers: {
    setQuery: (state, action) => {
      state.query = action.payload
    },
    selectEnterprise: (state, action) => {
      state.selectedNumber = action.payload
    },
    clearSelection: (state) => {
      state.selectedNumber = null
    },
  },
})

export const { setQuery, selectEnterprise, clearSelection } = uiSlice.actions
export default uiSlice.reducer
