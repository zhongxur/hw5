import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import './App.css'
import { api, money, type AgentEvent, type Cash, type PendingAction, type Ticket, type TicketDetail } from './api'
import { TicketRail } from './components/TicketRail'
import { AgentFloor } from './components/AgentFloor'
import { Feed } from './components/Feed'
import { Till } from './components/Till'
import { SummaryCard } from './components/SummaryCard'

export default function App() {
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [selected, setSelected] = useState<number | null>(null)
  const [detail, setDetail] = useState<TicketDetail | null>(null)
  const [events, setEvents] = useState<AgentEvent[]>([])
  const [cash, setCash] = useState<Cash | null>(null)
  const [approvals, setApprovals] = useState<PendingAction[]>([])
  const [approver, setApprover] = useState('store manager')
  const [busy, setBusy] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [online, setOnline] = useState(true)
  const lastSeq = useRef(0)

  const refresh = useCallback(async () => {
    try {
      const [t, c, a] = await Promise.all([api.tickets(), api.cash(), api.approvals()])
      setTickets(t)
      setCash(c)
      setApprovals(a)
      setOnline(true)
      setSelected((s) => s ?? t[0]?.id ?? null)
    } catch {
      setOnline(false)
    }
  }, [])

  const pullEvents = useCallback(async () => {
    try {
      const fresh = await api.events(lastSeq.current)
      if (fresh.length) {
        lastSeq.current = Math.max(lastSeq.current, fresh[fresh.length - 1].seq)
        // two polls can overlap (StrictMode, slow network) — keep each seq once
        setEvents((old) => {
          const seen = new Set(old.map((e) => e.seq))
          return [...old, ...fresh.filter((e) => !seen.has(e.seq))]
        })
      }
    } catch { /* offline banner handles it */ }
  }, [])

  // poll faster while any ticket is running
  const anyRunning = tickets.some((t) => t.running)
  useEffect(() => {
    refresh()
    pullEvents()
    const id = setInterval(() => {
      refresh()
      pullEvents()
    }, anyRunning ? 900 : 2500)
    return () => clearInterval(id)
  }, [refresh, pullEvents, anyRunning])

  useEffect(() => {
    if (selected == null) return
    let live = true
    api.ticket(selected).then((d) => { if (live) setDetail(d) }).catch(() => {})
    return () => { live = false }
  }, [selected, tickets, approvals.length])

  const ticket = tickets.find((t) => t.id === selected) ?? null
  // events of the latest run on the selected ticket (+ human clicks after it)
  const runEvents = useMemo(() => {
    const mine = events.filter((e) => e.ticket_id === selected)
    const lastStart = [...mine].reverse().find((e) => e.type === 'run_start' && e.depth === 0)
    if (!lastStart) return mine.filter((e) => e.agent === 'human')
    return mine.filter((e) => e.seq >= lastStart.seq - 1)
  }, [events, selected])
  const path = useMemo(
    () => runEvents.filter((e) => e.type === 'delegate').map((e) => `${e.agent}->${String(e.args?.to)}`),
    [runEvents],
  )

  async function start() {
    if (!ticket) return
    setError(null)
    try {
      await api.run(ticket.id)
      await refresh()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  async function decide(id: number, ok: boolean) {
    setBusy(id)
    setError(null)
    try {
      await (ok ? api.approve(id, approver) : api.reject(id, approver))
      await refresh()
      await pullEvents()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(null)
    }
  }

  async function reset() {
    if (!confirm('Reset the working database to the original values? Prepared actions and payments are cleared.')) return
    setError(null)
    try {
      await api.reset()
      setEvents([])
      lastSeq.current = 0
      setDetail(null)
      await refresh()
      await pullEvents()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  return (
    <div className="desk">
      <header className="masthead">
        <div className="brand">
          <span className="brand-mark">CC</span>
          <div>
            <h1>Campus Customs <em>Front Desk</em></h1>
            <p>Five agents, one counter on Chapel Street. They prepare — you sign.</p>
          </div>
        </div>
        <div className="masthead-right">
          {cash && (
            <div className="calendar" title="desk.date_today — every agent uses this date">
              <span>{new Date(cash.desk_date_today + 'T12:00').toLocaleString('en-US', { month: 'short' })}</span>
              <b>{cash.desk_date_today.slice(8)}</b>
            </div>
          )}
          <button className="btn-ghost" onClick={reset}>Reset database</button>
        </div>
      </header>

      {!online && <div className="banner">Can’t reach the backend at localhost:8000 — start it with <code>uvicorn main:app --reload --port 8000</code>.</div>}
      {error && <div className="banner banner-err">{error}</div>}

      <main className="layout">
        <TicketRail tickets={tickets} selected={selected} onSelect={setSelected} />

        <section className="center">
          {ticket && (
            <div className="ticket-head">
              <div>
                <span className="eyebrow">Ticket #{ticket.id} · {ticket.requester}</span>
                <h2>{ticket.subject}</h2>
                <p className="ticket-facts">
                  {ticket.sku && <span>{ticket.qty} × {ticket.sku} · size {ticket.size}</span>}
                  {ticket.invoice_id && <span>linked invoice #{ticket.invoice_id}</span>}
                  {ticket.lease_id && <span>linked lease #{ticket.lease_id}</span>}
                  <span>“{ticket.notes}”</span>
                </p>
              </div>
              <button
                className="btn-primary"
                onClick={start}
                disabled={ticket.running || ticket.status === 'resolved'}
              >
                {ticket.running ? 'Team is on it…' : ticket.status === 'resolved' ? 'Resolved' : detail?.summary ? 'Run again' : 'Send to the team'}
              </button>
            </div>
          )}
          <AgentFloor events={runEvents.filter((e) => e.agent !== 'human')} path={path} />
          {detail && <SummaryCard detail={detail} />}
          <Feed events={runEvents} />
        </section>

        <Till
          cash={cash}
          approvals={approvals}
          approver={approver}
          setApprover={setApprover}
          onDecide={decide}
          busy={busy}
        />
      </main>
      <footer className="foot">
        Agents: gpt-6-luna via Portkey · shop data via MCP over campus_customs_new.db ·
        {cash && <> {cash.payments.length} approved payment{cash.payments.length === 1 ? '' : 's'} totalling {money(cash.payments.reduce((s, p) => s + p.amount, 0))}</>}
      </footer>
    </div>
  )
}
