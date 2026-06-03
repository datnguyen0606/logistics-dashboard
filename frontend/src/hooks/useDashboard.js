import { useState, useEffect } from 'react'
import { api } from '../api/client'

function toParams(filters) {
  const p = {}
  if (filters.from_date) p.from_date = filters.from_date
  if (filters.to_date)   p.to_date   = filters.to_date
  if (filters.carrier)   p.carrier   = filters.carrier
  if (filters.region)    p.region    = filters.region
  if (filters.category)  p.category  = filters.category
  return p
}

export function useDashboard(filters) {
  const [kpi, setKpi] = useState(null)
  const [charts, setCharts] = useState({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)

    const params = toParams(filters)

    Promise.all([
      api.get('/api/kpi', { params }),
      api.get('/api/charts/order-volume', { params }),
      api.get('/api/charts/delivery-performance', { params }),
      api.get('/api/charts/carrier-breakdown', { params }),
      api.get('/api/charts/region-breakdown', { params }),
    ])
      .then(([kpiRes, volRes, perfRes, carrierRes, regionRes]) => {
        if (cancelled) return
        setKpi(kpiRes.data)
        setCharts({
          orderVolume:         volRes.data,
          deliveryPerformance: perfRes.data,
          carrierBreakdown:    carrierRes.data,
          regionBreakdown:     regionRes.data,
        })
      })
      .catch((err) => {
        if (!cancelled) setError(err.message || 'Failed to load dashboard data')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => { cancelled = true }
  }, [
    filters.from_date, filters.to_date,
    filters.carrier, filters.region, filters.category,
  ])

  return { kpi, charts, loading, error }
}
