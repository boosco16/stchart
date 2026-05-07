import { isAuthenticated } from './_lib/session.js'

export default async function handler(req, res) {
  const ok = await isAuthenticated(req)
  if (!ok) return res.status(401).json({ error: 'Unauthorized' })
  res.json({ ok: true })
}
