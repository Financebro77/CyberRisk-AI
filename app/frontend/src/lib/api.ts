/**
 * Typed fetch client for the CyberRisk AI API.
 *
 * Every endpoint returns a JSON-serialisable dict from the existing tool
 * layer.  The completeness guard (`{"status":"insufficient_info",...}`) is a
 * normal HTTP 200 response — callers inspect the `status` field rather than
 * relying on HTTP error codes.
 */
import type {
  ApiResult,
  ChatSession,
  ChatTurnRequest,
  ChatTurnResponse,
  CompanyBrief,
  ControlImprovementResponse,
  ExecutiveReportResponse,
  HealthResponse,
  InsuranceOptimiseResponse,
  InsuranceResponse,
  MethodologyResponse,
  PolicyInput,
  ReportResponse,
  ScenarioSummary,
  ScoreResponse,
  SimulationResponse,
} from './types';

const BASE = '/api';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (typeof body?.detail === 'string') detail = body.detail;
    } catch {
      /* non-JSON error body */
    }
    // Attach the status so callers can distinguish "session is gone" (404)
    // from transient network/engine failures.
    const err = new Error(detail) as Error & { status?: number };
    err.status = res.status;
    throw err;
  }
  return (await res.json()) as T;
}

function post<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export const api = {
  health: () => request<HealthResponse>('/health'),

  score: (brief: CompanyBrief) => post<ApiResult<ScoreResponse>>('/score', brief),

  simulate: (brief: CompanyBrief & { n_years?: number }) =>
    post<ApiResult<SimulationResponse>>('/simulate', brief),

  insurance: (body: CompanyBrief & PolicyInput & { n_years?: number }) =>
    post<ApiResult<InsuranceResponse>>('/insurance', body),

  insuranceOptimise: (body: CompanyBrief & PolicyInput & { n_years?: number }) =>
    post<ApiResult<InsuranceOptimiseResponse>>('/insurance/optimise', body),

  controlsImprovement: (
    body: CompanyBrief & { control_change: string; n_years?: number },
  ) => post<ApiResult<ControlImprovementResponse>>('/controls-improvement', body),

  report: (brief: CompanyBrief) => post<ApiResult<ReportResponse>>('/report', brief),

  reportDownloadUrl: () => '/api/report/download',

  executiveReport: (brief: CompanyBrief & PolicyInput) =>
    post<ApiResult<ExecutiveReportResponse>>('/report/executive', brief),

  methodology: () => request<MethodologyResponse>('/model/methodology'),

  chat: {
    createSession: () =>
      request<{ session_id: string }>('/chat/sessions', { method: 'POST' }),
    turn: (sessionId: string, req: ChatTurnRequest) =>
      request<ChatTurnResponse>(`/chat/${sessionId}/turns`, {
        method: 'POST',
        body: JSON.stringify(req),
      }),
    /** One persisted conversation (resume / sidebar refresh). */
    getSession: (sessionId: string) => request<ChatSession>(`/chat/sessions/${sessionId}`),
    /** Bulk-fetch the persisted conversations the browser owns (sidebar). */
    listSessions: (ids: string[]) =>
      request<{ sessions: ChatSession[] }>(
        `/chat/sessions?ids=${encodeURIComponent(ids.join(','))}`,
      ),
    renameSession: (sessionId: string, title: string) =>
      request<{ status: string }>(`/chat/sessions/${sessionId}`, {
        method: 'PATCH',
        body: JSON.stringify({ title }),
      }),
    deleteSession: (sessionId: string) =>
      request<{ status: string }>(`/chat/${sessionId}`, { method: 'DELETE' }),
  },

  scenarios: () => request<{ scenarios: ScenarioSummary[]; simulation: { default_years: number; copula_model: string } }>('/scenarios'),
};
