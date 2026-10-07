# Campus Customs Front Desk — React board

React + Vite + TypeScript board for the HW5 agent team. It talks to the FastAPI backend at
`http://localhost:8000` (override with `VITE_API_URL`).

```bash
npm install
npm run dev     # http://localhost:5173
```

Components: `TicketRail` (ticket spike), `AgentFloor` (five agent cards + hand-off relay),
`SummaryCard` (what the team did), `Feed` (live wire), `Till` (balance, approval tray, receipt tape).
Design notes: `../output/design.md`.
