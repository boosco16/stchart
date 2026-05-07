import { isAuthenticated } from '../_lib/session.js'

export default async function handler(req, res) {
  if (!await isAuthenticated(req)) return res.status(401).json({ error: 'Unauthorized' })

  const ticker = req.query.ticker?.toUpperCase()
  if (!ticker) return res.status(400).json({ error: 'No ticker' })

  try {
    const url = `https://query2.finance.yahoo.com/v8/finance/chart/${ticker}?interval=1d&range=1d`
    const r = await fetch(url, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://finance.yahoo.com',
        'Origin': 'https://finance.yahoo.com',
      }
    })

    if (!r.ok) return res.status(404).json({ error: 'Ticker not found' })

    const data = await r.json()
    const result = data?.chart?.result?.[0]
    if (!result) return res.status(404).json({ error: 'Ticker not found' })

    const meta = result.meta
    const quote = result.indicators?.quote?.[0]

    const price = meta.regularMarketPrice ?? 0
    const prevClose = meta.chartPreviousClose ?? meta.previousClose ?? 0
    const high = quote?.high?.[0] ?? 0
    const low = quote?.low?.[0] ?? 0
    const volume = quote?.volume?.[0] ?? 0
    const avgVolume = meta.averageDailyVolume10Day ?? meta.averageDailyVolume3Month ?? 1
    const change = price - prevClose
    const changePct = prevClose ? (change / prevClose) * 100 : 0
    const volumeBuzz = parseFloat((volume / avgVolume).toFixed(2))

    res.setHeader('Cache-Control', 's-maxage=30')
    res.json({
      ticker,
      name: meta.longName || meta.shortName || ticker,
      price,
      high,
      low,
      volume,
      prevClose,
      change,
      changePct,
      volumeBuzz,
    })
  } catch (e) {
    res.status(500).json({ error: e.message })
  }
}
