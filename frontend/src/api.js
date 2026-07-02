import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react'

// Couche d'accès au backend FastAPI. RTK Query gère cache, états de chargement et
// invalidation ; les composants consomment les hooks générés (useSearchQuery, ...).
export const api = createApi({
  reducerPath: 'api',
  baseQuery: fetchBaseQuery({ baseUrl: '/api' }),
  endpoints: (builder) => ({
    search: builder.query({
      query: (q) => `/search?q=${encodeURIComponent(q)}&limit=20`,
    }),
    enterprise: builder.query({
      query: (number) => `/enterprise/${number}`,
    }),
    directors: builder.query({
      query: (number) => `/enterprise/${number}/directors`,
    }),
  }),
})

export const { useSearchQuery, useEnterpriseQuery, useLazyDirectorsQuery } = api
