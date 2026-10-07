import type { Ticket } from '../api'

const TYPE_LABEL: Record<string, string> = {
  customer_order: 'Customer order',
  rent_notice: 'Rent notice',
  price_override: 'Price override',
}

const STATUS_LABEL: Record<Ticket['status'], string> = {
  open: 'Open',
  in_progress: 'Agents working',
  awaiting_approval: 'Needs your OK',
  resolved: 'Resolved',
}

export function TicketRail({
  tickets, selected, onSelect,
}: { tickets: Ticket[]; selected: number | null; onSelect: (id: number) => void }) {
  return (
    <aside className="rail">
      <div className="rail-head">
        <span className="eyebrow">Ticket spike</span>
        <span className="rail-count">{tickets.filter((t) => t.status !== 'resolved').length} open</span>
      </div>
      {tickets.map((t) => (
        <button
          key={t.id}
          className={`stub stub-${t.status} ${selected === t.id ? 'is-selected' : ''}`}
          onClick={() => onSelect(t.id)}
        >
          <div className="stub-top">
            <span className="stub-no">#{t.id}</span>
            <span className={`pill pill-${t.status}`}>
              {t.running && <span className="dot-pulse" />}
              {STATUS_LABEL[t.status]}
            </span>
          </div>
          <div className="stub-subject">{t.subject}</div>
          <div className="stub-meta">
            {TYPE_LABEL[t.type] ?? t.type} · {t.requester}
          </div>
          <div className="stub-note">{t.notes}</div>
          {t.status === 'resolved' && <div className="stamp stamp-small">Resolved</div>}
          <div className="stub-perf" aria-hidden />
        </button>
      ))}
    </aside>
  )
}
