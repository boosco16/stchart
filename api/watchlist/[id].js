import { isAuthenticated } from '../_lib/session.js'
import { supabase } from '../_lib/supabase.js'

export default async function handler(req, res) {
  if (!await isAuthenticated(req)) return res.status(401).json({ error: 'Unauthorized' })
  const { id } = req.query

  if (req.method === 'DELETE') {
    const { error } = await supabase.from('watchlist').delete().eq('id', id)
    if (error) return res.status(500).json({ error: error.message })
    return res.json({ ok: true })
  }

  if (req.method === 'PATCH') {
    const { data, error } = await supabase.from('watchlist')
      .update({ ...req.body, updated_at: new Date().toISOString() })
      .eq('id', id).select().single()
    if (error) return res.status(500).json({ error: error.message })
    return res.json(data)
  }

  res.status(405).end()
}
