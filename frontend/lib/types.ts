export type UserRole =
  | "administrator"
  | "procurement_manager"
  | "buyer"
  | "requester"
  | "supplier_manager"
  | "category_manager"
  | "ap_clerk"
  | "contract_manager";

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  tenant_id?: string;
}

export interface Token {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface AiProviderResponse {
  current_provider: string;
  available_providers: string[];
}

export interface Requisition {
  id: string;
  requisition_number?: string | null;
  title: string;
  description?: string | null;
  request_type: string;
  status: string;
  lifecycle_status: string;
  requested_by: string;
  supplier_id?: string | null;
  currency: string;
  estimated_value?: string | null;
  approval_status: string;
  priority: string;
  commodity?: string | null;
  category?: string | null;
  account_code?: string | null;
  need_by_date?: string | null;
  notes?: string | null;
  created_at: string;
  updated_at: string;
}

export interface RequisitionListResponse {
  items: Requisition[];
  total: number;
  skip: number;
  limit: number;
}

export type SupplierLifecycleStatus =
  | "active"
  | "under_monitoring"
  | "requalification_due"
  | "requalification_in_progress"
  | "offboarding"
  | "offboarded"
  | "merged";

export type SupplierRelationshipType = "subsidiary" | "affiliate" | "branch" | "plant";

export interface Supplier {
  id: string;
  name: string;
  description?: string | null;
  contact_email?: string | null;
  contact_phone?: string | null;
  address?: string | null;
  website?: string | null;
  tax_id?: string | null;
  payment_terms?: string | null;
  currency: string;
  is_active: boolean;
  lifecycle_status: SupplierLifecycleStatus;
  last_qualified_at?: string | null;
  next_requalification_due_at?: string | null;
  offboarding_reason?: string | null;
  offboarded_at?: string | null;
  parent_supplier_id?: string | null;
  relationship_type?: SupplierRelationshipType | null;
  merged_into_supplier_id?: string | null;
  created_at: string;
  updated_at: string;
}

export interface SupplierListResponse {
  items: Supplier[];
  total: number;
  skip: number;
  limit: number;
}

export interface SupplierHierarchyNode {
  id: string;
  name: string;
  relationship_type?: SupplierRelationshipType | null;
}

export interface SupplierHierarchyResponse {
  supplier_id: string;
  parent: SupplierHierarchyNode | null;
  children: SupplierHierarchyNode[];
}

export interface SupplierSpendRollupResponse {
  supplier_id: string;
  included_supplier_ids: string[];
  total_spend: string;
}

export interface SupplierDuplicateCandidate {
  supplier_id: string;
  name: string;
  match_score: number;
  match_reasons: string[];
}

export interface SupplierDuplicatesResponse {
  supplier_id: string;
  candidates: SupplierDuplicateCandidate[];
}

export interface AgentQueryResponse {
  agent_name: string;
  success: boolean;
  message: string;
  data: Record<string, unknown>;
  plan: string[];
  explanation: string;
}

export interface AgentActivityLogEntry {
  id: string;
  agent_name: string;
  request_text: string;
  success: boolean;
  message: string;
  plan: unknown[];
  explanation?: string | null;
  tools_used: string[];
  llm_used: boolean;
  data: Record<string, unknown>;
  actor_id?: string | null;
  latency_ms?: number | null;
  created_at: string;
}

export interface AgentActivityLogListResponse {
  items: AgentActivityLogEntry[];
  total: number;
  limit: number;
  offset: number;
}

export interface AgentActivitySummaryResponse {
  total_calls: number;
  success_count: number;
  failure_count: number;
  llm_used_count: number;
  by_agent: Record<string, number>;
}

export interface Contract {
  id: string;
  title: string;
  description?: string | null;
  contract_number: string;
  supplier_id: string;
  contract_type: string;
  status: string;
  lifecycle_status: string;
  approval_status: string;
  start_date: string;
  end_date?: string | null;
  value?: string | null;
  currency: string;
  auto_renew: boolean;
  renewal_notice_days: number;
  terms_and_conditions?: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface ContractListResponse {
  items: Contract[];
  total: number;
  skip: number;
  limit: number;
}

export interface Document {
  id: string;
  filename: string;
  content_type: string;
  file_size: number;
  document_type: string;
  storage_path: string;
  content?: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface DocumentListResponse {
  items: Document[];
  total: number;
  skip: number;
  limit: number;
}

export interface SourcingEvent {
  id: string;
  event_number: string;
  title: string;
  description?: string | null;
  event_type: string;
  category?: string | null;
  owner_id: string;
  currency: string;
  estimated_value?: string | null;
  start_date?: string | null;
  response_due_date?: string | null;
  status: string;
  lifecycle_status: string;
  awarded_supplier_id?: string | null;
  awarded_response_id?: string | null;
  award_notes?: string | null;
  created_at: string;
  updated_at: string;
  published_at?: string | null;
  closed_at?: string | null;
  cancelled_at?: string | null;
  line_items: Array<{
    id: string;
    event_id: string;
    description: string;
    quantity: string;
    unit_of_measure?: string | null;
    target_price?: string | null;
    specifications?: string | null;
    created_at: string;
  }>;
  invitations: Array<{
    id: string;
    event_id: string;
    supplier_id: string;
    status: string;
    invited_by: string;
    invited_at: string;
    responded_at?: string | null;
  }>;
  responses: Array<{
    id: string;
    event_id: string;
    supplier_id: string;
    invitation_id?: string | null;
    total_price?: string | null;
    currency: string;
    notes?: string | null;
    status: string;
    evaluation_score?: string | null;
    evaluation_notes?: string | null;
    rank?: number | null;
    submitted_at: string;
    evaluated_at?: string | null;
  }>;
}

export interface SourcingEventListResponse {
  items: SourcingEvent[];
  total: number;
  skip: number;
  limit: number;
}

export interface DashboardMetricsResponse {
  total_spend: string;
  total_suppliers: number;
  total_contracts: number;
  active_contracts: number;
  expiring_contracts: number;
  pending_approvals: number;
  spend_by_category: Array<{ category: string; amount: string; percentage: number }>;
  spend_by_month: Array<{ month: string; amount: string }>;
  top_suppliers: Array<{ supplier_id: string; supplier_name: string; total_spend: string; contract_count: number }>;
}

export interface SpendAnalyticsResponse {
  total_spend: string;
  currency: string;
  spend_by_category: Array<{ category: string; amount: string }>;
  spend_by_month: Array<{ month: string; amount: string }>;
  top_suppliers: Array<{ supplier_name: string; total_spend: string }>;
}

export interface SavingsSummaryResponse {
  total_savings: string;
  total_baseline: string;
  total_actual: string;
  savings_by_category: Record<string, string>;
  savings_by_type: Record<string, string>;
}

export interface SavingsRecord {
  id: string;
  description: string;
  category?: string | null;
  source_type: string;
  source_id?: string | null;
  savings_type: string;
  baseline_amount: string;
  actual_amount: string;
  savings_amount: string;
  currency: string;
  realized_date: string;
  notes?: string | null;
  recorded_by: string;
  created_at: string;
}

export interface SavingsListResponse {
  items: SavingsRecord[];
  total: number;
  skip: number;
  limit: number;
  summary: SavingsSummaryResponse;
}

export interface WorkflowDefinition {
  id: string;
  name: string;
  entity_type: string;
  description?: string | null;
  steps: Array<Record<string, unknown>>;
  is_active: boolean;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface WorkflowDefinitionListResponse {
  items: WorkflowDefinition[];
  total: number;
  skip: number;
  limit: number;
}

export interface WorkflowTask {
  id: string;
  instance_id: string;
  step_index: number;
  step_name: string;
  assignee_id: string;
  status: string;
  due_at?: string | null;
  escalate_to?: string | null;
  escalated_at?: string | null;
  comments?: string | null;
  completed_by?: string | null;
  completed_at?: string | null;
  created_at: string;
}

export interface WorkflowInstance {
  id: string;
  definition_id: string;
  entity_type: string;
  entity_id: string;
  status: string;
  current_step_index: number;
  context: Record<string, unknown>;
  started_by: string;
  started_at: string;
  completed_at?: string | null;
  tasks: WorkflowTask[];
}

export interface WorkflowInstanceListResponse {
  items: WorkflowInstance[];
  total: number;
  skip: number;
  limit: number;
}

export interface Notification {
  id: string;
  recipient_id: string;
  title: string;
  message: string;
  related_entity_type?: string | null;
  related_entity_id?: string | null;
  is_read: boolean;
  created_at: string;
  read_at?: string | null;
}

export interface NotificationListResponse {
  items: Notification[];
  total: number;
  unread_count: number;
  skip: number;
  limit: number;
}

export type DocumentType =
  | "procurement_requisition"
  | "purchase_order"
  | "goods_receipt"
  | "procurement_invoice";

export type ResetCadence = "monthly" | "yearly" | "never";

export interface DocumentNumberingFormat {
  document_type: DocumentType;
  prefix: string;
  pattern: string;
  sequence_padding: number;
  reset_cadence: ResetCadence;
  is_customized: boolean;
  sample: string;
  updated_at?: string | null;
}

export interface DocumentNumberingFormatListResponse {
  items: DocumentNumberingFormat[];
}

export interface DocumentNumberingPreviewResponse {
  sample: string;
  next_number: string;
}
