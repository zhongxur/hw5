export const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export type Role = 'boss' | 'inventory' | 'accounting' | 'facilities' | 'customer_service'

export interface Ticket {
  id: number
  type: string
  requester: string
  subject: string
  sku: string | null
  size: string | null
  qty: number | null
  lease_id: number | null
  invoice_id: number | null
  status: 'open' | 'in_progress' | 'awaiting_approval' | 'resolved'
  notes: string | null
  created_at: string
  outcome: string | null
  running: boolean
  pending_count: number
}

export interface AgentEvent {
  seq: number
  ts: string
  run_id: string
  ticket_id: number
  agent: Role | 'human'
  depth: number
  step: number
  type:
    | 'run_start' | 'thinking' | 'tool_call' | 'tool_result' | 'delegate' | 'delegate_result'
    | 'message' | 'final' | 'error' | 'run_end' | 'human'
  tool: string | null
  args: Record<string, unknown> | null
  text: string | null
}

export interface PendingAction {
  id: number
  ticket_id: number
  kind: 'invoice_payment' | 'rent_payment' | 'purchase_order' | 'price_override'
  ref_id: number | null
  amount: number
  description: string
  payload: Record<string, unknown>
  requested_by: string
  status: 'pending' | 'approved' | 'rejected'
  created_at: string
  decided_at: string | null
  decided_by: string | null
}

export interface Payment {
  id: number
  kind: string
  ref_id: number
  amount: number
  account: string
  paid_at: string
  approved_by: string
}

export interface Cash {
  balance: number
  balance_date: string
  desk_date_today: string
  committed_outflows: number
  available_after_commitments: number
  open_invoices: { id: number; amount: number; due_date: string }[]
  rent_due_within_7_days: { id: number; space_name: string; monthly_rent: number; next_due: string }[]
  payments: Payment[]
}

export interface Summary {
  run_id: string
  ticket_id: number
  status: string
  error?: string
  report?: {
    ticket_id: number
    outcome: string
    contributions: { agent: Role; did: string }[]
    human_approvals_needed: string[]
    customer_message_queued: boolean
  }
  delegation_path?: string[]
  tools_by_agent?: Record<string, string[]>
  usage?: { requests: number; input_tokens: number; output_tokens: number; total_tokens: number }
}

export interface TicketDetail {
  ticket: Ticket
  running: boolean
  pending_actions: PendingAction[]
  customer_messages: { id: number; recipient: string; message: string; status: string; created_at: string }[]
  summary: Summary | null
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(API + path, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!r.ok) {
    const body = await r.json().catch(() => ({}))
    throw new Error(body.detail ?? `${r.status} ${r.statusText}`)
  }
  return r.json() as Promise<T>
}

export const api = {
  tickets: () => req<Ticket[]>('/api/tickets'),
  ticket: (id: number) => req<TicketDetail>(`/api/tickets/${id}`),
  run: (id: number) => req<{ started: boolean }>(`/api/tickets/${id}/run`, { method: 'POST' }),
  events: (since: number) => req<AgentEvent[]>(`/api/events?since=${since}`),
  approvals: () => req<PendingAction[]>('/api/approvals?status=pending'),
  approve: (id: number, approver: string) =>
    req(`/api/approvals/${id}/approve`, { method: 'POST', body: JSON.stringify({ approver }) }),
  reject: (id: number, approver: string) =>
    req(`/api/approvals/${id}/reject`, { method: 'POST', body: JSON.stringify({ approver }) }),
  cash: () => req<Cash>('/api/cash'),
  reset: () => req<{ checking_balance: number }>('/api/reset', { method: 'POST' }),
}

export const AGENTS: { role: Role; label: string; title: string; mark: string }[] = [
  { role: 'boss', label: 'Boss', title: 'Desk lead · dispatches', mark: 'B' },
  { role: 'customer_service', label: 'Customer Service', title: 'Talks to buyers', mark: 'CS' },
  { role: 'inventory', label: 'Inventory', title: 'Stockroom & vendors', mark: 'IN' },
  { role: 'accounting', label: 'Accounting', title: 'Cash, invoices, prices', mark: '$' },
  { role: 'facilities', label: 'Facilities', title: 'Lease & landlord', mark: 'FA' },
]

export const LABEL: Record<string, string> = Object.fromEntries(
  [...AGENTS.map((a) => [a.role, a.label]), ['human', 'Manager']],
)

export const money = (n: number) =>
  n.toLocaleString('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2 })
