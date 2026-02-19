import { createClient } from '@sanity/client'

export const client = createClient({
  projectId: '95zjvqmu',
  dataset: 'production',
  useCdn: true, // true = fast, cached data
  apiVersion: '2025-01-27', // use current date (YYYY-MM-DD format)
})
