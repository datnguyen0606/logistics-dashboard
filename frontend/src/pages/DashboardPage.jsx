import { useState } from 'react'
import FilterBar from '../components/FilterBar'
import KPICard from '../components/KPICard'
import ChartWrapper from '../components/ChartWrapper'
import { useDashboard } from '../hooks/useDashboard'

const DEFAULT_FILTERS = {
  from_date: null,
  to_date:   null,
  carrier:   null,
  region:    null,
  category:  null,
}

export default function DashboardPage() {
  const [filters, setFilters] = useState(DEFAULT_FILTERS)
  const { kpi, charts, loading, error } = useDashboard(filters)

  return (
    <div className="page">
      <FilterBar filters={filters} onFilterChange={setFilters} />

      {error && <div className="error-banner">{error}</div>}

      {loading ? (
        <div className="loading">Loading dashboard…</div>
      ) : kpi?.total_orders === 0 ? (
        <div className="empty-state">No orders match the selected filters</div>
      ) : (
        <>
          <div className="kpi-grid">
            <KPICard label="Total Orders"       value={kpi?.total_orders} />
            <KPICard label="Delivered"           value={kpi?.delivered_orders} />
            <KPICard label="Delayed"             value={kpi?.delayed_orders} />
            <KPICard label="On-Time Rate"        value={kpi?.on_time_rate} unit="%" />
            <KPICard label="Avg Delivery Days"   value={kpi?.avg_delivery_days} unit="days" />
            <KPICard label="Total Order Value"   value={kpi ? `$${kpi.total_order_value.toLocaleString()}` : null} />
          </div>

          <div className="charts-grid">
            <ChartWrapper chartSpec={charts.orderVolume} />
            <ChartWrapper chartSpec={charts.deliveryPerformance} />
            <ChartWrapper chartSpec={charts.carrierBreakdown} />
            <ChartWrapper chartSpec={charts.regionBreakdown} />
          </div>
        </>
      )}
    </div>
  )
}
