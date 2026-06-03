const CARRIERS = ['DHL', 'FedEx', 'UPS', 'USPS', 'GLS', 'DPD', 'Royal Mail', 'LaserShip', 'OnTrac']
const REGIONS   = ['UK', 'EU', 'US-C', 'US-E', 'US-W']
const CATEGORIES = ['PAPER', 'BOOK', 'CRAYON', 'PENCIL', 'MARKER', 'STICKER', 'BRUSH', 'PAINT']

export default function FilterBar({ filters, onFilterChange }) {
  const set = (key) => (e) => onFilterChange({ ...filters, [key]: e.target.value || null })

  return (
    <div className="filter-bar">
      <label className="filter-group">
        <span>From</span>
        <input type="date" value={filters.from_date || ''} onChange={set('from_date')} />
      </label>
      <label className="filter-group">
        <span>To</span>
        <input type="date" value={filters.to_date || ''} onChange={set('to_date')} />
      </label>
      <label className="filter-group">
        <span>Carrier</span>
        <select value={filters.carrier || ''} onChange={set('carrier')}>
          <option value="">All carriers</option>
          {CARRIERS.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
      </label>
      <label className="filter-group">
        <span>Region</span>
        <select value={filters.region || ''} onChange={set('region')}>
          <option value="">All regions</option>
          {REGIONS.map(r => <option key={r} value={r}>{r}</option>)}
        </select>
      </label>
      <label className="filter-group">
        <span>Category</span>
        <select value={filters.category || ''} onChange={set('category')}>
          <option value="">All categories</option>
          {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
      </label>
    </div>
  )
}
