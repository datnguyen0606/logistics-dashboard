export default function ExplainabilityPanel({ explainability }) {
  if (!explainability) return null
  const { intent, tool_used, filters = {}, metric, group_by, node_trace = [] } = explainability

  const filterEntries = Object.entries(filters).filter(([, v]) => v)

  return (
    <details className="explainability-panel">
      <summary>Explainability</summary>
      <div className="explainability-body">
        <div className="explainability-row">
          <span className="explainability-key">Intent</span>
          <span className="explainability-badge">{intent}</span>
        </div>
        {tool_used && (
          <div className="explainability-row">
            <span className="explainability-key">Tool</span>
            <span className="explainability-badge">{tool_used}</span>
          </div>
        )}
        {metric && (
          <div className="explainability-row">
            <span className="explainability-key">Metric</span>
            <span>{metric} by {group_by}</span>
          </div>
        )}
        {filterEntries.length > 0 && (
          <div className="explainability-row">
            <span className="explainability-key">Filters</span>
            <span>{filterEntries.map(([k, v]) => `${k}: ${v}`).join(' · ')}</span>
          </div>
        )}
        <div className="explainability-row">
          <span className="explainability-key">Steps</span>
          <span className="node-trace">{node_trace.join(' → ')}</span>
        </div>
      </div>
    </details>
  )
}
