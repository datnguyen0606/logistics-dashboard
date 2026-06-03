import { useState } from 'react'
import QueryInput from '../components/QueryInput'
import ChartWrapper from '../components/ChartWrapper'
import ExplainabilityPanel from '../components/ExplainabilityPanel'
import DataTable from '../components/DataTable'
import { useQuery } from '../hooks/useQuery'

export default function QueryPage() {
  const { answerText, chart, explainability, underlyingData, loading, error, askQuestion } = useQuery()
  const [history, setHistory] = useState([])
  const [activeResult, setActiveResult] = useState(null)

  const handleSubmit = (question) => {
    setActiveResult(null)
    askQuestion(question)
  }

  // Save to history when a complete result arrives
  const handleComplete = (question, result) => {
    setHistory(prev => [{question, result, id: Date.now()}, ...prev].slice(0, 20))
  }

  const restoreHistory = (item) => {
    setActiveResult(item.result)
  }

  const displayChart         = activeResult ? activeResult.chart         : chart
  const displayExplainability = activeResult ? activeResult.explainability : explainability
  const displayData          = activeResult ? activeResult.underlyingData  : underlyingData
  const displayAnswer        = activeResult ? activeResult.answer          : answerText

  return (
    <div className="query-page">
      <div className="query-main">
        <QueryInput onSubmit={handleSubmit} loading={loading} />

        {error && <div className="error-banner">{error}</div>}

        {(displayAnswer || loading) && (
          <div className="answer-block">
            {displayAnswer && <p className="answer-text">{displayAnswer}</p>}
            {loading && !displayAnswer && <span className="answer-cursor">▋</span>}
          </div>
        )}

        {displayChart && <ChartWrapper chartSpec={displayChart} />}
        {displayExplainability && <ExplainabilityPanel explainability={displayExplainability} />}
        {displayData?.length > 0 && <DataTable data={displayData} />}
      </div>

      {history.length > 0 && (
        <aside className="query-history">
          <h3>Query History</h3>
          <ul>
            {history.map(item => (
              <li key={item.id}>
                <button className="history-item" onClick={() => restoreHistory(item)}>
                  {item.question}
                </button>
              </li>
            ))}
          </ul>
        </aside>
      )}
    </div>
  )
}
