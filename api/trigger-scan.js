import { isAuthenticated } from './_lib/session.js'

export default async function handler(req, res) {
  if (req.method !== 'POST') return res.status(405).end()
  if (!await isAuthenticated(req)) return res.status(401).json({ error: 'Unauthorized' })

  const [owner, repo] = process.env.GITHUB_REPO.split('/')

  const r = await fetch(`https://api.github.com/repos/${owner}/${repo}/actions/workflows/scanner.yml/dispatches`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${process.env.GITHUB_TOKEN}`,
      'Accept': 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ ref: 'main' }),
  })

  if (r.status === 204) {
    res.json({ ok: true })
  } else {
    const data = await r.json().catch(() => ({}))
    res.status(500).json({ error: data.message || 'Failed to trigger scan' })
  }
}
