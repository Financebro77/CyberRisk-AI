/**
 * TypeScript mirrors of the FastAPI / tool-layer response shapes.
 * These map 1:1 to the JSON dicts returned by the existing
 * `cyberrisk.agent.tools` functions (see src/cyberrisk/agent/tools.py).
 */

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
}

export interface CompanyBrief {
  firm_name?: string;
  industry?: string | null;
  revenue_usd?: number | null;
  customer_records?: number | null;
  technology_dependency?: string | null;
  security_controls?: string | null;
  previous_incidents?: number;
  existing_coverage?: string | null;
  risk_appetite?: string | null;
  /** Optional structured extras the form maps onto the backend fields above.
   *  Not part of the CompanyBrief DTO — sent as hints, dropped by the API. */
  country?: string;
  employees?: number;
  sensitive_records?: string;
  cloud_dependency?: string;
  third_party_dependency?: string;
  mfa_coverage?: string;
  pam?: string;
  network_segmentation?: string;
  backup_strategy?: string;
  vulnerability_management?: string;
  incident_response?: string;
  policy_limit?: number;
  retention?: number;
}

export interface PolicyInput {
  per_occurrence_deductible?: number;
  per_occurrence_limit?: number | null;
  annual_aggregate_deductible?: number;
  annual_aggregate_limit?: number | null;
  coinsurance?: number;
}

/** Completeness guard returned when revenue/controls are missing. */
export interface InsufficientInfo {
  status: 'insufficient_info';
  needed: string[];
  message: string;
}

export interface ScoreResponse {
  status: 'ok';
  firm_name: string;
  risk_score: number;
  risk_category: string;
  risk_drivers: string[];
  domain_scores: Record<string, number>;
  assumed_factors: string[];
}

export interface ScenarioContributionDetail {
  scenario_key: string;
  scenario_name: string;
  contribution: number;
  aal: number;
  frequency_drivers: string[];
  severity_drivers: string[];
  recommended_controls: string[];
  linked_to_model: boolean;
}

export interface SimulationResponse {
  status: 'ok';
  firm_name: string;
  risk_score: number;
  risk_category: string;
  risk_drivers: string[];
  n_years: number;
  eal: number;
  var_95: number;
  var_99: number;
  es_95: number;
  es_99: number;
  pml_1in200: number;
  pml_1in1000: number;
  prob_zero_loss: number;
  loss_distribution: {
    p50: number;
    p90: number;
    p95: number;
    p99: number;
    p99_9: number;
  };
  loss_exceedance: Array<{ loss: number; prob: number }>;
  aal_by_scenario: Record<string, number>;
  scenario_contribution: Record<string, number>;
  scenario_contribution_detail: ScenarioContributionDetail[];
}

export interface InsuranceResponse {
  status: 'ok';
  firm_name: string;
  ground_up_loss: {
    eal: number;
    var_95: number;
    var_99: number;
    es_95: number;
    es_99: number;
    pml_1in1000: number;
  };
  policy: PolicyInput & {
    per_occurrence_limit: number | null;
    annual_aggregate_limit: number | null;
  };
  insurance_response: {
    policy_limit: number;
    retention: number;
    covered_loss: number;
    insurer_payment: number;
    p_annual_limit_exhausted: number;
  };
  client_retained_loss: {
    retained_eal: number;
    retained_es_99: number;
    gross_loss_at_p99_9: number;
    insurance_recovery_at_p99_9: number;
    residual_exposure_at_p99_9: number;
  };
  pml_1in1000: number;
  evaluation: {
    residual_uncovered: boolean;
    summary: string;
  };
}

/** One evaluated insurance structure (current or recommended). */
export interface InsuranceStructure {
  policy_limit: number;
  retention: number;
  insurer_payment: number;
  p_annual_limit_exhausted: number;
  residual_exposure: number;
  evaluation: {
    residual_uncovered: boolean;
    summary: string;
  };
}

/** Response of /api/insurance/optimise. */
export interface InsuranceOptimiseResponse {
  status: 'ok';
  firm_name: string;
  ground_up_loss: InsuranceResponse['ground_up_loss'];
  current: {
    ground_up_loss: InsuranceResponse['ground_up_loss'];
    policy: PolicyInput & { per_occurrence_limit: number | null; annual_aggregate_limit: number | null };
    insurance_response: InsuranceResponse['insurance_response'];
    client_retained_loss: InsuranceResponse['client_retained_loss'];
    pml_1in1000: number;
    evaluation: InsuranceResponse['evaluation'];
  };
  recommended: InsuranceStructure;
}

/** Executive report data — aggregated by /api/report/executive. */
export interface ExecutiveReportResponse {
  status: 'ok';
  firm_name: string;
  executive_summary: {
    risk_score: number;
    risk_category: string;
    sentence: string;
  };
  risk_rating: {
    score: number;
    category: string;
    domain_scores: Record<string, number>;
    risk_drivers: string[];
  };
  financial_exposure: {
    eal: number;
    var_95: number;
    var_99: number;
    es_99: number;
    pml_1in200: number;
    pml_1in1000: number;
    loss_distribution: {
      p50: number;
      p90: number;
      p95: number;
      p99: number;
      p99_9: number;
    };
    prob_zero_loss: number;
  };
  insurance_analysis: {
    ground_up_loss: InsuranceResponse['ground_up_loss'];
    insurance_response: InsuranceResponse['insurance_response'];
    client_retained_loss: InsuranceResponse['client_retained_loss'];
    evaluation: InsuranceResponse['evaluation'];
  };
  mitigation_roadmap: Array<{
    scenario_key: string;
    scenario_name: string;
    contribution: number;
    aal: number;
    frequency_drivers: string[];
    severity_drivers: string[];
    recommended_controls: string[];
    linked_to_model: boolean;
  }>;
  scenario_contributions: Record<string, number>;
  model_limitations: {
    heading: string;
    limitations: string[];
  };
}

export interface ControlImprovementResponse {
  status: 'ok';
  control_change: string;
  label: string;
  factor_key: string;
  target_rating: string;
  before: { eal: number; var_99: number; es_99: number };
  after: { eal: number; var_99: number; es_99: number };
  impact: {
    loss_reduction: number;
    percentage_improvement: number;
  };
}

export interface ReportResponse {
  status: 'ok';
  report_path: string;
  firm_name: string;
  risk_category: string;
  eal: number;
  var_99: number;
  es_99: number;
}

export interface MethodologyResponse {
  sections: {
    scoring_methodology: string;
    frequency_adjustments: string;
    severity_adjustments: string;
    simulation_methodology: string;
  };
}

export interface ScenarioSummary {
  key: string;
  name: string;
  frequency_model: string;
  lambda_annual: number;
  severity_model: string;
}

export interface ScenariosResponse {
  scenarios: ScenarioSummary[];
  simulation: {
    default_years: number;
    copula_model: string;
  };
}

export type ApiResult<T> = T | InsufficientInfo | { status: 'error'; error: string };

/* ------------------------------------------------------------------ */
/* Consultant chat                                                      */
/* ------------------------------------------------------------------ */

/** A tool call that actually ran this turn, with its full result. */
export interface ChatToolTrace {
  name: string;
  arguments: Record<string, unknown>;
  ok: boolean;
  error?: string | null;
  data: Record<string, unknown>;
}

export interface ChatTurnRequest {
  message: string;
  welcome?: boolean;
}

/** One message the chat transcript renders (consultant + voice client). */
export interface TranscriptMessage {
  role: 'user' | 'assistant';
  content: string;
  toolTrace: ChatToolTrace[];
  safety?: { class_name: string; response: string } | null;
}

export interface ChatTurnResponse {
  session_id: string;
  role: string;
  content: string;
  tool_trace: ChatToolTrace[];
  history: Array<{ role: string; content: string }>;
  safety: { class_name: string; response: string } | null;
  model: string;
}

/** One persisted message row in a chat-session payload. */
export interface ChatHistoryMessage {
  role: string;
  content: string;
  /** The tool trace for THIS message (charts re-render on resume). */
  tool_trace: ChatToolTrace[] | null;
}

/** A persisted conversation (GET /chat/sessions/{id} and the bulk list). */
export interface ChatSession {
  session_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  history: ChatHistoryMessage[];
}
