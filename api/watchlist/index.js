import { isAuthenticated } from '../_lib/session.js'
import { supabase } from '../_lib/supabase.js'

export default async function handler(req, res) {
  if (!await isAuthenticated(req)) return res.status(401).json({ error: 'Unauthorized' })

  if (req.method === 'GET') {
    const { data, error } = await supabase.from('watchlist').select('*').order('added_at', { ascending: false })
    if (error) return res.status(500).json({ error: error.message })
    return res.json(data)
  }

  if (req.method === 'POST') {
    const { ticker, avg_cost, shares, notes } = req.body
    const { data, error } = await supabase.from('watchlist')
      .insert({ ticker: ticker.toUpperCase(), avg_cost: avg_cost || null, shares: shares || 0, notes: notes || null })
      .select().single()
    if (error) return res.status(500).json({ error: error.message })
    return res.json(data)
  }

  res.status(405).end()
}
