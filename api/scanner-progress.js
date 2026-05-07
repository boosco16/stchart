import { isAuthenticated } from './_lib/session.js'
import { supabase } from './_lib/supabase.js'

export default async function handler(req, res) {
  if (!await isAuthenticated(req)) return res.status(401).json({ error: 'Unauthorized' })

  res.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate')
  res.setHeader('Pragma', 'no-cache')

  const { data, error } = await supabase
    .from('scanner_progress')
    .select('*')
    .eq('id', 1)
    .single()

  if (error) return res.status(500).json({ error: error.message })
  res.json(data)
}
