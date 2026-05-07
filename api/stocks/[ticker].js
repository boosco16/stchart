import { isAuthenticated } from '../_lib/session.js'

export default async function handler(req, res) {
  if (!await isAuthenticated(req)) return res.status(401).json({ error: 'Unauthorized' })

  const ticker = req.query.ticker?.toUpperCase()
  if (!ticker) return res.status(400).json({ error: 'No ticker' })

  try {
    const url = `https://stooq.com/q/d/l/?s=${ticker}.US&i=d`
    const r = await fetch(url, {
      headers: { 'User-Agent': 'Mozilla/5.0' }
    })

    if (!r.ok) return res.status(404).json({ error: 'Ticker not found' })

    const text = await r.text()
    const lines = text.trim().split('\n')

    // Need at least header + 2 data rows
    if (lines.length < 3) return res.status(404).json({ error: 'Ticker not found' })

    // Parse rows — header is: Date,Open,High,Low,Close,Volume
    const rows = lines.slice(1).map(line => {
      const [date, open, high, low, close, volume] = line.split(',')
      return {
        date,
        open: parseFloat(open),
        high: parseFloat(high),
        low: parseFloat(low),
        close: parseFloat(close),
        volume: parseInt(volume) || 0
      }
    }).filter(r => !isNaN(r.close) && r.close > 0)

    if (rows.length < 2) return res.status(404).json({ error: 'Insufficient data' })

    const today = rows[rows.length - 1]
    const yesterday = rows[rows.length - 2]

    // Average volume over last 20 days
    const recent = rows.slice(-20)
    const avgVolume = recent.reduce((sum, r) => sum + r.volume, 0) / recent.length

    const price = today.close
    const prevClose = yesterday.close
    const change = price - prevClose
    const changePct = prevClose ? (change / prevClose) * 100 : 0
    const volumeBuzz = avgVolume ? parseFloat((today.volume / avgVolume).toFixed(2)) : 1

    res.setHeader('Cache-Control', 's-maxage=60')
    res.json({
      ticker,
      name: ticker,
      price,
      high: today.high,
      low: today.low,
      open: today.open,
      volume: today.volume,
      prevClose,
      change,
      changePct,
      volumeBuzz,
    })
  } catch (e) {
    res.status(500).json({ error: e.message })
  }
}
