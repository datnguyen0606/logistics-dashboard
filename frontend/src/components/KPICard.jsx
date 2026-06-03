export default function KPICard({ label, value, unit = '' }) {
  return (
    <div className="kpi-card">
      <span className="kpi-label">{label}</span>
      <span className="kpi-value">
        {value !== null && value !== undefined ? value : '—'}
        {unit && <span className="kpi-unit"> {unit}</span>}
      </span>
    </div>
  )
}
