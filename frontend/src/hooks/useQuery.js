import { useState, useCallback } from 'react'
import { fetchStream } from '../api/client'

export function useQuery() {
  const [answerText, setAnswerText]         = useState('')
  const [chart, setChart]                   = useState(null)
  const [explainability, setExplainability] = useState(null)
  const [underlyingData, setUnderlyingData] = useState([])
  const [loading, setLoading]               = useState(false)
  const [error, setError]                   = useState(null)

  const askQuestion = useCallback((question) => {
    setAnswerText('')
    setChart(null)
    setExplainability(null)
    setUnderlyingData([])
    setError(null)
    setLoading(true)

    fetchStream(
      '/api/query/ask',
      { question },
      (token) => setAnswerText(prev => prev + token),
      (complete) => {
        setChart(complete.chart || null)
        setExplainability(complete.explainability || null)
        setUnderlyingData(complete.underlying_data || [])
        setLoading(false)
      },
      (err) => {
        setError(err)
        setLoading(false)
      },
    )
  }, [])

  return { answerText, chart, explainability, underlyingData, loading, error, askQuestion }
}
