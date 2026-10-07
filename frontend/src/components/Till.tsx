import { useEffect, useRef, useState } from 'react'
import { money, type Cash, type PendingAction } from '../api'

/** Animates the balance down (or up) like a mechanical till. */
function useTicker(target: number) {
  const [shown, setShown] = useState(target)
  const from = useRef(target)
  useEffect(() => {
    const start = performance.now()
    const a = from.current
    let raf = 0
    const tick = (t: number) => {
      const k = Math.min(1, (t - start) / 900)
      const eased = 1 - Math.pow(1 - k, 3)
      setShown(a + (target - a) * eased)
      if (k < 1) raf = requestAnimationFrame(tick)
      else from.current = target
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [target])
  return shown
}

const KIND_LABEL: Record<PendingAction['kind'], string> = {
  invoice_payment: 'Vendor invoice',
  rent_payment: 'Rent',
  purchase_order: 'Restock purchase',
  price_override: 'Price override',
}

export function Till({
  cash, approvals, approver, setApprover, onDecide, busy,
}: {
  cash: Cash | null
  approvals: PendingAction[]
  approver: string
  setApprover: (s: string) => void
  onDecide: (id: number, ok: boolean) => void
  busy: number | null
}) {
  const bal = useTicker(cash?.balance ?? 0)
  const after = cash ? cash.balance - approvals.reduce((s, a) => s + a.amount, 0) : 0
  return (
    <aside className="till">
      <section className="register">
        <span className="eyebrow light">Checking · cash_accounts</span>
        <div className="register-amount">{money(bal)}</div>
        <div className="register-sub">
          as of {cash?.balance_date ?? '—'}
          {approvals.length > 0 && <> · {money(after)} if all approved</>}
        </div>
        <div className="register-split">
          <div>
            <span>Committed</span>
            <b>{money(cash?.committed_outflows ?? 0)}</b>
          </div>
          <div>
            <span>Free to spend</span>
            <b className={(cash?.available_after_commitments ?? 0) < 300 ? 'warn' : ''}>
              {money(cash?.available_after_commitments ?? 0)}
            </b>
          </div>
        </div>
      </section>

      <section className="tray">
        <div className="tray-head">
          <span className="eyebrow">Approval tray</span>
          <span className="tray-count">{approvals.length}</span>
        </div>
        <label className="approver">
          Signing as
          <input value={approver} onChange={(e) => setApprover(e.target.value)} />
        </label>
        {approvals.length === 0 && <p className="tray-empty">Nothing waiting. Agents can only prepare money moves — they land here for you.</p>}
        {approvals.map((a) => (
          <article key={a.id} className={`slip slip-${a.kind}`}>
            <div className="slip-top">
              <span>{KIND_LABEL[a.kind]} · ticket #{a.ticket_id}</span>
              <b>{a.amount > 0 ? `−${money(a.amount)}` : '$0 cash'}</b>
            </div>
            <p>{a.description}</p>
            <div className="slip-meta">prepared by {a.requested_by.replace('_', ' ')} · #{a.id}</div>
            <div className="slip-actions">
              <button className="btn-stamp" disabled={busy === a.id} onClick={() => onDecide(a.id, true)}>
                Approve
              </button>
              <button className="btn-ghost" disabled={busy === a.id} onClick={() => onDecide(a.id, false)}>
                Reject
              </button>
            </div>
          </article>
        ))}
      </section>

      <section className="tape">
        <span className="eyebrow">Receipt tape · payments</span>
        {(cash?.payments ?? []).length === 0 && <p className="tape-empty">No money has left the till.</p>}
        {(cash?.payments ?? []).map((p) => (
          <div key={p.id} className="tape-row">
            <span>{p.paid_at} · {p.kind} #{p.ref_id}</span>
            <b>−{money(p.amount)}</b>
            <span className="tape-by">ok’d by {p.approved_by}</span>
          </div>
        ))}
      </section>
    </aside>
  )
}
