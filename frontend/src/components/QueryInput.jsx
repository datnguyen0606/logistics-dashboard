import { useState } from 'react'

const PROMPT_CHIPS = [
  'Which carrier has the highest delay rate?',
  'Show delayed orders by week for Q3',
  'Predict demand for BOOK next 3 months',
]

export default function QueryInput({ onSubmit, loading }) {
  const [text, setText] = useState('')

  const submit = (q) => {
    const question = (q || text).trim()
    if (!question || loading) return
    onSubmit(question)
    setText('')
  }

  return (
    <div className="query-input-wrapper">
      <div className="prompt-chips">
        {PROMPT_CHIPS.map(chip => (
          <button
            key={chip}
            className="prompt-chip"
            onClick={() => submit(chip)}
            disabled={loading}
          >
            {chip}
          </button>
        ))}
      </div>
      <div className="query-row">
        <textarea
          className="query-textarea"
          rows={2}
          placeholder="Ask a question about your logistics data…"
          value={text}
          onChange={e => setText(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit() } }}
          disabled={loading}
        />
        <button className="ask-button" onClick={() => submit()} disabled={!text.trim() || loading}>
          {loading ? '…' : 'Ask'}
        </button>
      </div>
    </div>
  )
}
