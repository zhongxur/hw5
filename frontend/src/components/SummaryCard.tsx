import { LABEL, type TicketDetail } from '../api'

export function SummaryCard({ detail }: { detail: TicketDetail }) {
  const s = detail.summary
  if (!s) return null
  if (s.error) return <section className="summary"><p className="err">Run failed: {s.error}</p></section>
  const r = s.report!
  return (
    <section className={`summary ${detail.ticket.status === 'resolved' ? 'is-resolved' : ''}`}>
      {detail.ticket.status === 'resolved' && <div className="stamp">Resolved</div>}
      <span className="eyebrow">What the team did</span>
      <h3>{r.outcome}</h3>
      <ul className="contrib">
        {r.contributions.map((c, i) => (
          <li key={i} className={`who-${c.agent}`}>
            <span className={`chip chip-${c.agent}`}>{LABEL[c.agent]}</span>
            <div>
              <p>{c.did}</p>
              {s.tools_by_agent?.[c.agent] && (
                <div className="tools-used">
                  {s.tools_by_agent[c.agent].map((t) => <code key={t}>{t}</code>)}
                </div>
              )}
            </div>
          </li>
        ))}
      </ul>
      {detail.customer_messages.length > 0 && (
        <div className="letter">
          <span className="eyebrow">Reply queued for {detail.customer_messages.at(-1)!.recipient}</span>
          <p>{detail.customer_messages.at(-1)!.message}</p>
        </div>
      )}
      <div className="summary-foot">
        {s.usage && (
          <span>
            {s.usage.requests} model calls · {s.usage.total_tokens.toLocaleString()} tokens
          </span>
        )}
        {detail.pending_actions.map((a) => (
          <span key={a.id} className={`decision decision-${a.status}`}>
            #{a.id} {a.status}{a.decided_by ? ` by ${a.decided_by}` : ''}
          </span>
        ))}
      </div>
    </section>
  )
}
