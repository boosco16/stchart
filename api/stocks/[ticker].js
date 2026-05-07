import { isAuthenticated } from '../_lib/session.js'

export default async function handler(req, res) {
  if (!await isAuthenticated(req)) return res.status(401).json({ error: 'Unauthorized' })

  const ticker = req.query.ticker?.toUpperCase()
  if (!ticker) return res.status(400).json({ error: 'No ticker' })

  try {
    // Try query1 first, fall back to query2
    let data = null
    for (const host of ['query1', 'query2']) {
      try {
        const url = `https://${host}.finance.yahoo.com/v8/finance/chart/${ticker}?interval=1d&range=5d`
        const r = await fetch(url, {
          headers: {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Referer': 'https://finance.yahoo.com/',
            'Origin': 'https://finance.yahoo.com',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-site',
          }
        })
        if (r.ok) {
          const json = await r.json()
          if (json?.chart?.result?.[0]) {
            data = json
            break
          }
        }
      } catch {}
    }

    if (!data) return res.status(404).json({ error: 'Ticker not found' })

    const result = data.chart.result[0]
    const meta = result.meta
    const quotes = result.indicators?.quote?.[0]
    const closes = result.indicators?.adjclose?.[0]?.adjclose ?? []

    // Get today's and yesterday's data
    const timestamps = result.timestamp ?? []
    const lastIdx = timestamps.length - 1
    const prevIdx = lastIdx - 1

    const price = meta.regularMarketPrice ?? quotes?.close?.[lastIdx] ?? 0
    const prevClose = meta.chartPreviousClose ?? quotes?.close?.[prevIdx] ?? 0
    const high = quotes?.high?.[lastIdx] ?? meta.regularMarketDayHigh ?? 0
    const low = quotes?.low?.[lastIdx] ?? meta.regularMarketDayLow ?? 0
    const open = quotes?.open?.[lastIdx] ?? 0
    const volume = quotes?.volume?.[lastIdx] ?? meta.regularMarketVolume ?? 0
    const avgVolume = meta.averageDailyVolume10Day ?? meta.averageDailyVolume3Month ?? 1
    const change = price - prevClose
    const changePct = prevClose ? (change / prevClose) * 100 : 0
    const volumeBuzz = avgVolume ? parseFloat((volume / avgVolume).toFixed(2)) : 1

    res.setHeader('Cache-Control', 's-maxage=30')
    res.json({
      ticker,
      name: meta.longName || meta.shortName || ticker,
      price,
      high,
      low,
      open,
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
