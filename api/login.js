import { createToken, setCookie } from './_lib/session.js'

export default async function handler(req, res) {
  if (req.method !== 'POST') return res.status(405).end()

  const { username, password } = req.body

  if (username === process.env.ADMIN_USERNAME && password === process.env.ADMIN_PASSWORD) {
    const token = await createToken()
    setCookie(res, token)
    return res.json({ ok: true })
  }

  return res.status(401).json({ error: 'Invalid credentials' })
}
