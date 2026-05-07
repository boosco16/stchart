import { clearCookie } from './_lib/session.js'

export default function handler(req, res) {
  clearCookie(res)
  res.json({ ok: true })
}
