import { AGENTS, type AgentEvent, type Role } from '../api'

type State = 'idle' | 'thinking' | 'tool' | 'waiting' | 'done'

interface AgentView {
  state: State
  line: string
  tools: number
  handoffs: number
}

/** Folds the event stream of the current run into one status card per agent. */
function deriveViews(events: AgentEvent[]): Record<Role, AgentView> {
  const v = Object.fromEntries(
    AGENTS.map((a) => [a.role, { state: 'idle', line: '', tools: 0, handoffs: 0 } as AgentView]),
  ) as Record<Role, AgentView>
  for (const e of events) {
    if (e.agent === 'human') continue
    const a = v[e.agent]
    switch (e.type) {
      case 'run_start':
        a.state = 'thinking'
        a.line = e.depth === 0 ? 'Reading the ticket…' : `Asked: ${e.text ?? ''}`
        break
      case 'tool_call':
        a.state = 'tool'
        a.tools += 1
        a.line = `${e.tool}(${e.args ? Object.values(e.args).join(', ') : ''})`
        break
      case 'tool_result':
        a.state = 'thinking'
        break
      case 'delegate':
        a.state = 'waiting'
        a.handoffs += 1
        a.line = `Handed to ${String(e.args?.to ?? '').replace('_', ' ')}`
        break
      case 'delegate_result':
        a.state = 'thinking'
        break
      case 'message':
        a.line = e.text ?? ''
        break
      case 'final':
        a.state = 'done'
        a.line = e.text ?? ''
        break
      case 'error':
        a.line = `⚠ ${e.text ?? ''}`
        break
    }
  }
  return v
}

const STATE_LABEL: Record<State, string> = {
  idle: 'Idle',
  thinking: 'Thinking',
  tool: 'Using a tool',
  waiting: 'Waiting on colleague',
  done: 'Done',
}

function shortLine(raw: string) {
  const s = raw.replace(/\*\*/g, '').replace(/^#+\s*/gm, '').replace(/^\s*[-*]\s+/gm, '• ')
  if (s.startsWith('{')) {
    try {
      const o = JSON.parse(s)
      if (o.outcome) return o.outcome as string
    } catch {
      // long reports are truncated in the event feed, so pull the outcome out by hand
      const m = s.match(/"outcome":\s*"((?:[^"\\]|\\.)*)/)
      if (m) return m[1].length > 220 ? m[1].slice(0, 220) + '…' : m[1]
    }
  }
  return s.length > 220 ? s.slice(0, 220) + '…' : s
}

export function AgentFloor({ events, path }: { events: AgentEvent[]; path: string[] }) {
  const views = deriveViews(events)
  return (
    <section className="floor">
      <div className="floor-grid">
        {AGENTS.map((a) => {
          const vw = views[a.role]
          return (
            <article key={a.role} className={`agent agent-${a.role} state-${vw.state}`}>
              <header>
                <span className="agent-mark">{a.mark}</span>
                <div>
                  <div className="agent-name">{a.label}</div>
                  <div className="agent-title">{a.title}</div>
                </div>
              </header>
              <span className="agent-state">{STATE_LABEL[vw.state]}</span>
              <p className="agent-line">{vw.line ? shortLine(vw.line) : <em>Not on this ticket yet</em>}</p>
              <footer>
                <span>{vw.tools} tool call{vw.tools === 1 ? '' : 's'}</span>
                <span>{vw.handoffs} hand-off{vw.handoffs === 1 ? '' : 's'}</span>
              </footer>
            </article>
          )
        })}
      </div>
      {path.length > 0 && (
        <div className="relay">
          <span className="eyebrow">Hand-off relay</span>
          <div className="relay-chain">
            {path.map((p, i) => {
              const [from, to] = p.split('->')
              return (
                <span key={i} className="relay-hop">
                  <span className={`chip chip-${from}`}>{from.replace('_', ' ')}</span>
                  <span className="relay-arrow">→</span>
                  <span className={`chip chip-${to}`}>{to.replace('_', ' ')}</span>
                </span>
              )
            })}
          </div>
        </div>
      )}
    </section>
  )
}
