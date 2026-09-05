import { Activity, AlertTriangle, Bot, CheckCircle2, Database, ShieldCheck } from 'lucide-react';

const workflowSteps = [
  'Failed Payment',
  'Revenue-at-Risk Detection',
  'Customer Context',
  'AI Diagnosis',
  'Policy Validation',
  'Recovery Action',
  'Audit Trail',
];

const metrics = [
  { label: 'Seeded cases', value: '80' },
  { label: 'Recovery actions', value: '4' },
  { label: 'Policy limits', value: '3' },
  { label: 'Provider mode', value: 'Stub' },
];

export function App() {
  return (
    <main className="min-h-screen bg-[#f6f7f9] text-ink">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="grid h-9 w-9 place-items-center rounded bg-mint text-white">
              <Activity size={20} />
            </div>
            <div>
              <h1 className="text-lg font-semibold">FluxPay</h1>
              <p className="text-sm text-slate-500">AI Revenue Recovery Agent</p>
            </div>
          </div>
          <div className="flex items-center gap-2 rounded border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600">
            <Database size={16} />
            Foundation MVP
          </div>
        </div>
      </header>

      <section className="mx-auto grid max-w-7xl gap-8 px-6 py-8 lg:grid-cols-[1.25fr_0.75fr]">
        <div>
          <div className="mb-6 flex items-center gap-2 text-sm font-medium text-coral">
            <AlertTriangle size={18} />
            Failed-payment recovery workspace
          </div>
          <h2 className="max-w-3xl text-4xl font-semibold tracking-normal text-ink">
            Detect revenue at risk and prepare validated recovery actions.
          </h2>
          <p className="mt-4 max-w-2xl text-base leading-7 text-slate-600">
            This shell is wired for the first milestone: API health, database schema, migrations,
            seed data, and a clean boundary for future LLM-driven decisions.
          </p>

          <div className="mt-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {metrics.map((metric) => (
              <div key={metric.label} className="rounded border border-slate-200 bg-white p-4">
                <p className="text-sm text-slate-500">{metric.label}</p>
                <p className="mt-2 text-2xl font-semibold">{metric.value}</p>
              </div>
            ))}
          </div>
        </div>

        <aside className="rounded border border-slate-200 bg-white p-5">
          <div className="flex items-center gap-2 border-b border-slate-100 pb-4 font-medium">
            <ShieldCheck size={18} className="text-mint" />
            Guardrails
          </div>
          <div className="mt-4 space-y-4 text-sm text-slate-600">
            <p>LLM output is structured and isolated behind a provider interface.</p>
            <p>Backend services own validation, policy limits, financial calculations, and actions.</p>
            <p>Payment processing is simulated for the hackathon MVP.</p>
          </div>
        </aside>
      </section>

      <section className="mx-auto max-w-7xl px-6 pb-10">
        <div className="rounded border border-slate-200 bg-white p-5">
          <div className="mb-5 flex items-center gap-2 font-medium">
            <Bot size={18} className="text-gold" />
            Core Workflow
          </div>
          <div className="grid gap-3 md:grid-cols-7">
            {workflowSteps.map((step, index) => (
              <div key={step} className="min-h-28 rounded border border-slate-200 bg-slate-50 p-3">
                <div className="mb-4 flex h-7 w-7 items-center justify-center rounded bg-white text-sm font-semibold text-slate-700">
                  {index + 1}
                </div>
                <p className="text-sm font-medium leading-5">{step}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <footer className="mx-auto flex max-w-7xl items-center gap-2 px-6 pb-8 text-sm text-slate-500">
        <CheckCircle2 size={16} className="text-mint" />
        Backend health endpoint: <code className="rounded bg-white px-2 py-1">/health</code>
      </footer>
    </main>
  );
}
