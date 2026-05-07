import { isAuthenticated } from '../_lib/session.js'

const AV_KEY = process.env.ALPHAVANTAGE_KEY

export default async function handler(req, res) {
  if (!await isAuthenticated(req)) return res.status(401).json({ error: 'Unauthorized' })

  const ticker = req.query.ticker?.toUpperCase()
  if (!ticker) return res.status(400).json({ error: 'No ticker' })

  try {
    const url = `https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol=${ticker}&apikey=${AV_KEY}`
    const r = await fetch(url)
    const data = await r.json()

    const q = data['Global Quote']
    if (!q || !q['05. price']) {
      return res.status(404).json({ error: `Ticker not found: ${ticker}` })
    }

    const price = parseFloat(q['05. price'])
    const open = parseFloat(q['02. open'])
    const high = parseFloat(q['03. high'])
    const low = parseFloat(q['04. low'])
    const prevClose = parseFloat(q['08. previous close'])
    const volume = parseInt(q['06. volume'])
    const change = parseFloat(q['09. change'])
    const changePct = parseFloat(q['10. change percent'].replace('%', ''))

    // Fetch 20 day average volume for buzz
    const dailyUrl = `https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol=${ticker}&outputsize=compact&apikey=${AV_KEY}`
    const dailyR = await fetch(dailyUrl)
    const dailyData = await dailyR.json()
    const series = dailyData['Time Series (Daily)']

    let volumeBuzz = 1
    if (series) {
      const days = Object.values(series).slice(0, 20)
      const avgVol = days.reduce((sum, d) => sum + parseInt(d['5. volume']), 0) / days.length
      volumeBuzz = avgVol ? parseFloat((volume / avgVol).toFixed(2)) : 1
    }

    res.setHeader('Cache-Control', 's-maxage=60')
    res.json({
      ticker,
      name: ticker,
      price,
      open,
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
