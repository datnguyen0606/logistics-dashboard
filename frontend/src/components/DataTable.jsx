import { useState } from 'react'

export default function DataTable({ data = [] }) {
  const [open, setOpen] = useState(false)

  if (!data.length) return null

  const columns = Object.keys(data[0])

  return (
    <div className="data-table-wrapper">
      <button className="data-table-toggle" onClick={() => setOpen(o => !o)}>
        {open ? '▾' : '▸'} Underlying data ({data.length} rows)
      </button>
      {open && (
        <div className="data-table-scroll">
          <table className="data-table">
            <thead>
              <tr>{columns.map(c => <th key={c}>{c}</th>)}</tr>
            </thead>
            <tbody>
              {data.map((row, i) => (
                <tr key={i}>
                  {columns.map(c => <td key={c}>{row[c] ?? '—'}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
