import { isAuthenticated } from './_lib/session.js'
import { supabase } from './_lib/supabase.js'

export default async function handler(req, res) {
  if (!await isAuthenticated(req)) return res.status(401).json({ error: 'Unauthorized' })

  const { data, error } = await supabase
    .from('scanner_results')
    .select('*')
    .order('setup_date', { ascending: false })
    .order('scanned_at', { ascending: false })
    .limit(25)

  if (error) return res.status(500).json({ error: error.message })
  res.json(data)
}
