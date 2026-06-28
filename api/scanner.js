import { isAuthenticated } from './_lib/session.js'
import { supabase } from './_lib/supabase.js'
import yahooFinance from 'yahoo-finance2'

export default async function handler(req, res) {
  if (!await isAuthenticated(req)) return res.status(401).json({ error: 'Unauthorized' })

  const { data, error } = await supabase
    .from('scanner_results')
    .select('*')
    .order('setup_date', { ascending: false })
    .order('scanned_at', { ascending: false })
    .limit(25)

  if (error) return res.status(500).json({ error: error.message })
  if (!data || data.length === 0) return res.json([])

  // Enrich with sector — parallel fetch for all unique tickers
  const tickers = [...new Set(data.map(r => r.ticker))]

  const sectorMap = {}
  await Promise.all(
    tickers.map(async ticker => {
      try {
        const quote = await yahooFinance.quoteSummary(
          ticker,
          { modules: ['assetProfile'] },
          { validateResult: false }
        )
        sectorMap[ticker] = quote.assetProfile?.sector || 'Unknown'
      } catch {
        sectorMap[ticker] = 'Unknown'
      }
    })
  )

  const enriched = data.map(r => ({ ...r, sector: sectorMap[r.ticker] || 'Unknown' }))
  res.json(enriched)
}
