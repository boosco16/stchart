import { isAuthenticated } from '../_lib/session.js'

const KEY = process.env.POLYGON_API_KEY
const BASE = 'https://api.polygon.io'

export default async function handler(req, res) {
  if (!await isAuthenticated(req)) return res.status(401).json({ error: 'Unauthorized' })

  const ticker = req.query.ticker?.toUpperCase()

  try {
    const [snapRes, refRes] = await Promise.all([
      fetch(`${BASE}/v2/snapshot/locale/us/markets/stocks/tickers/${ticker}?apiKey=${KEY}`),
      fetch(`${BASE}/v3/reference/tickers/${ticker}?apiKey=${KEY}`),
    ])
    const [snap, ref] = await Promise.all([snapRes.json(), refRes.json()])
    const s = snap.ticker
    if (!s) return res.status(404).json({ error: 'Not found' })

    const todayVol = s.day?.volume || 0
    const prevVol = s.prevDay?.volume || todayVol || 1

    res.setHeader('Cache-Control', 's-maxage=60')
    res.json({
      ticker,
      name: ref.results?.name || ticker,
      price: s.day?.close ?? s.lastTrade?.price ?? 0,
      open: s.day?.open ?? 0,
      high: s.day?.high ?? 0,
      low: s.day?.low ?? 0,
      volume: todayVol,
      prevClose: s.prevDay?.close ?? 0,
      change: s.todaysChange ?? 0,
      changePct: s.todaysChangePerc ?? 0,
      vwap: s.day?.vwap ?? 0,
      volumeBuzz: parseFloat((todayVol / prevVol).toFixed(2)),
    })
  } catch {
    res.status(500).json({ error: 'Failed to fetch' })
  }
}
