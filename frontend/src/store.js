import { configureStore } from '@reduxjs/toolkit'
import { api } from './api'
import uiReducer from './uiSlice'

export const store = configureStore({
  reducer: {
    [api.reducerPath]: api.reducer,
    ui: uiReducer,
  },
  middleware: (getDefaultMiddleware) => getDefaultMiddleware().concat(api.middleware),
})
