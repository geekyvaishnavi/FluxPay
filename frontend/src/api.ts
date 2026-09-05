const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

export type DashboardMetrics = {
  total_revenue_at_risk: string; total_recovered_revenue: string; recovery_rate: string;
  active_recovery_cases: number; total_recovery_cases: number; recovered_cases: number;
  retrying_cases: number; escalated_cases: number; stopped_cases: number;
};
export type RecoveryCase = {
  id: string; customer_name: string; customer_email: string; invoice_number: string;
  payment_amount: string; currency: string; failure_reason: string | null; revenue_at_risk: string;
  status: string; created_at: string; risk_level: string | null; recommended_action: string | null;
};
export type RecoveryRun = {
  run_id: string; started_at: string; finished_at: string | null; cases_processed: number;
  actions_executed: number; recovered_cases: number; escalated_cases: number; stopped_cases: number;
  revenue_at_risk: string; revenue_recovered: string; recovery_rate: string;
};
export type RecoveryRunSummary = Omit<RecoveryRun, 'started_at' | 'finished_at'>;
export type CaseDetail = {
  id: string; status: string; revenue_at_risk: string; recovered_revenue: string; opened_at: string; closed_at: string | null;
  customer: { name: string; email: string; company_name: string | null; status: string };
  payment: { invoice_number: string; amount: string; currency: string; status: string; due_at: string; failure_reason: string | null };
  payment_history: { attempt_count: number; failed_attempts: number; latest_attempt_at: string | null };
  decision: { diagnosis: string; risk_level: string; recommended_action: string; confidence: string; reason: string; delay_hours: number; created_at: string } | null;
  policy_result: { allowed?: boolean; action?: string; reason?: string } | null;
  actions: Array<{ action_type: string; status: string; reason: string; result: Record<string, unknown>; executed_at: string | null; created_at: string }>;
};
export type AuditActivity = { id: string; recovery_case_id: string | null; event_type: string; actor: string; details: Record<string, unknown>; created_at: string };

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, { headers: { 'Content-Type': 'application/json', ...options?.headers }, ...options });
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(body?.detail ?? `Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  getMetrics: () => request<DashboardMetrics>('/dashboard/metrics'), getCases: () => request<RecoveryCase[]>('/recovery/cases'),
  getCase: (caseId: string) => request<CaseDetail>(`/recovery/cases/${caseId}`), getRuns: () => request<RecoveryRun[]>('/recovery/runs'),
  getAuditActivity: () => request<AuditActivity[]>('/recovery/audit-activity'),
  runRecovery: () => request<RecoveryRunSummary>('/recovery/run', { method: 'POST', body: '{}' }),
};
