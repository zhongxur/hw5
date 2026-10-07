import { useEffect, useRef } from 'react'
import { LABEL, type AgentEvent } from '../api'

function pretty(text: string | null) {
  if (!text) return ''
  if (text.startsWith('{') || text.startsWith('[')) {
    try {
      return JSON.stringify(JSON.parse(text), null, 1)
    } catch { /* keep raw */ }
  }
  return text
}

/** The live wire: one line per agent-loop step, indented by hand-off depth. */
export function Feed({ events }: { events: AgentEvent[] }) {
  const end = useRef<HTMLDivElement>(null)
  useEffect(() => {
    end.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [events.length])

  const shown = events.filter((e) => e.type !== 'run_end')
  return (
    <section className="feed">
      <div className="feed-head">
        <span className="eyebrow">Live wire</span>
        <span className="feed-count">{shown.length} steps</span>
      </div>
      <div className="feed-body">
        {shown.length === 0 && <div className="feed-empty">Pick a ticket and press “Send to the team”.</div>}
        {shown.map((e) => (
          <div
            key={e.seq}
            className={`line line-${e.type} who-${e.agent}`}
            style={{ marginLeft: `${Math.min(e.depth, 3) * 18}px` }}
          >
            <span className="line-who">{LABEL[e.agent] ?? e.agent}</span>
            {e.type === 'tool_call' && (
              <code className="line-tool">
                {e.tool}({e.args ? Object.entries(e.args).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(', ') : ''})
              </code>
            )}
            {e.type === 'tool_result' && (
              <details className="line-result">
                <summary>↳ {e.tool} returned</summary>
                <pre>{pretty(e.text)}</pre>
              </details>
            )}
            {e.type === 'delegate' && <span className="line-text">→ {e.text?.split(': ').slice(1).join(': ')}</span>}
            {e.type === 'delegate_result' && (
              <details className="line-result">
                <summary>← answer from {LABEL[String(e.args?.from)] ?? ''}</summary>
                <pre>{e.text}</pre>
              </details>
            )}
            {(e.type === 'message' || e.type === 'human') && <span className="line-text">{e.text}</span>}
            {e.type === 'run_start' && <span className="line-text dim">started · {e.depth === 0 ? 'ticket' : e.text}</span>}
            {e.type === 'final' && (
              <details className="line-result" open={e.depth === 0}>
                <summary>✓ final answer</summary>
                <pre>{pretty(e.text)}</pre>
              </details>
            )}
            {e.type === 'error' && <span className="line-text err">{e.tool ? `${e.tool}: ` : ''}{e.text}</span>}
          </div>
        ))}
        <div ref={end} />
      </div>
    </section>
  )
}
