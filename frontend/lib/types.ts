export type UserRole =
  | "administrator"
  | "procurement_manager"
  | "buyer"
  | "requester"
  | "supplier_manager"
  | "category_manager"
  | "ap_clerk"
  | "contract_manager";

export interface ActAsUserSummary {
  id: string;
  full_name: string;
  email: string;
  role: string;
}

export interface ActAsStatusResponse {
  is_impersonating: boolean;
  session_id?: string | null;
  admin_user?: ActAsUserSummary | null;
}

export interface ActAsStartResponse {
  session_id: string;
  access_token: string;
  token_type: string;
  expires_at: string;
  target_user: ActAsUserSummary;
  admin_user: ActAsUserSummary;
}

export interface ActAsSessionResponse {
  id: string;
  admin_user_id: string;
  target_user_id: string;
  started_at: string;
  expires_at: string;
  ended_at?: string | null;
  ended_reason?: string | null;
}

export interface ActAsSessionListResponse {
  items: ActAsSessionResponse[];
  total: number;
}

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  is_superuser: boolean;
  tenant_id?: string;
  // Only populated by GET /auth/me -- see ActAsStatusResponse. Absent (not
  // just false) on responses from other endpoints that embed a User.
  act_as?: ActAsStatusResponse;
}

export interface UserUpdate {
  email?: string;
  full_name?: string;
  role?: UserRole;
  is_active?: boolean;
  is_superuser?: boolean;
}

export interface UserListResponse {
  items: User[];
  total: number;
  skip: number;
  limit: number;
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

export interface RequisitionLineItem {
  id: string;
  requisition_id: string;
  description: string;
  quantity: string;
  unit_price?: string | null;
  line_total?: string | null;
  commodity?: string | null;
  category?: string | null;
  account_code?: string | null;
  created_at: string;
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
  is_emergency?: boolean;
  delay_until?: string | null;
  header_tax?: string | null;
  shipping_cost?: string | null;
  notes?: string | null;
  line_items: RequisitionLineItem[];
  created_at: string;
  updated_at: string;
}

export interface CommodityCodeResult {
  code: string;
  commodity_title?: string | null;
  class_title?: string | null;
  family_title?: string | null;
  segment_title?: string | null;
  is_active: boolean;
}

export interface CategoryResult {
  code: string;
  name?: string | null;
  is_active: boolean;
}

export interface RequisitionListResponse {
  items: Requisition[];
  total: number;
  skip: number;
  limit: number;
}

export interface Budget {
  id: string;
  tenant_id: string;
  fiscal_year: number;
  fiscal_period?: number | null;
  scope_level: string;
  scope_code: string;
  budgeted_amount: string;
  enforcement: string;
  created_by?: string | null;
  created_at: string;
  updated_at: string;
}

export interface BudgetCreate {
  fiscal_year: number;
  fiscal_period?: number | null;
  scope_level: string;
  scope_code: string;
  budgeted_amount: string;
  enforcement: string;
}

export interface BudgetUpdate {
  budgeted_amount?: string;
  enforcement?: string;
}

export interface BudgetCheckResponse {
  budget_id?: string | null;
  scope_level?: string | null;
  scope_code?: string | null;
  enforcement?: string | null;
  budgeted_amount?: string | null;
  committed: string;
  actual: string;
  available?: string | null;
  requested_amount: string;
  would_exceed: boolean;
  blocked: boolean;
  message?: string | null;
}

export interface BudgetListResponse {
  items: Budget[];
  total: number;
  skip: number;
  limit: number;
}

export interface AddressResult {
  id: string;
  label: string;
  owner_type?: string;
  owner_id?: string | null;
  address_line1?: string | null;
  city?: string | null;
  is_default?: boolean;
}

export interface AccountingSplit {
  id: string;
  split_method: "percentage" | "amount";
  percentage?: string | null;
  amount?: string | null;
  gl_account_code: string;
  cost_center?: string | null;
  department?: string | null;
  project_code?: string | null;
}

export interface PurchaseOrderLineItem {
  id: string;
  purchase_order_id: string;
  line_number: number;
  description: string;
  quantity: string;
  unit_price?: string | null;
  line_total?: string | null;
  account_code?: string | null;
  account_code_is_override: boolean;
  allocated_shipping_amount?: string | null;
  weight?: string | null;
  created_at: string;
}

export type PurchaseOrderLifecycleStatus =
  | "draft"
  | "pending_approval"
  | "approved"
  | "ordered"
  | "sent_to_supplier"
  | "acknowledged"
  | "partially_received"
  | "fully_received"
  | "invoiced"
  | "closed"
  | "cancelled";

export interface BudgetWarning {
  scope_level: string;
  scope_code: string;
  requested_amount: string;
  available: string;
  enforcement: string;
}

export interface PurchaseOrder {
  id: string;
  requisition_id: string;
  supplier_id?: string | null;
  order_number: string;
  status: string;
  lifecycle_status: PurchaseOrderLifecycleStatus;
  version_number: number;
  amendment_status: string;
  change_order_reference?: string | null;
  currency: string;
  subtotal?: string | null;
  tax_total?: string | null;
  shipping_amount?: string | null;
  shipping_allocation_method: string;
  grand_total?: string | null;
  total_amount?: string | null;
  incoterms?: string | null;
  payment_terms?: string | null;
  ship_to_address_id?: string | null;
  ship_to_name?: string | null;
  ship_to_address_line1?: string | null;
  ship_to_city?: string | null;
  bill_to_address_id?: string | null;
  bill_to_name?: string | null;
  bill_to_address_line1?: string | null;
  bill_to_city?: string | null;
  acknowledgment_status: string;
  acknowledged_at?: string | null;
  acknowledged_notes?: string | null;
  notes?: string | null;
  line_items: PurchaseOrderLineItem[];
  budget_warnings?: BudgetWarning[] | null;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface PurchaseOrderListResponse {
  items: PurchaseOrder[];
  total: number;
  skip: number;
  limit: number;
}

export interface GoodsReceiptLineItem {
  id: string;
  goods_receipt_id: string;
  purchase_order_line_item_id: string;
  quantity_received: number;
  quantity_rejected: number;
  quantity_accepted: number;
  rejection_reason?: string | null;
  lot_number?: string | null;
  condition_status: string;
  notes?: string | null;
  created_at: string;
}

export interface GoodsReceipt {
  id: string;
  purchase_order_id: string;
  receipt_number: string;
  status: string;
  receipt_type: string;
  received_quantity: number;
  returned_quantity: number;
  inspection_status: string;
  has_exceptions: boolean;
  approval_required: boolean;
  submitted_at?: string | null;
  approved_at?: string | null;
  posted_at?: string | null;
  rejected_at?: string | null;
  rejection_reason?: string | null;
  line_items: GoodsReceiptLineItem[];
  created_by: string;
  created_at: string;
}

export interface GrirRecord {
  id: string;
  purchase_order_id: string;
  purchase_order_line_item_id: string | null;
  total_ordered_qty: string;
  total_received_qty: string;
  total_invoiced_qty: string;
  balance_qty: string;
  balance_amount: string;
  status: string;
  last_updated_at: string | null;
}

export interface ProcurementInvoice {
  id: string;
  invoice_number: string;
  purchase_order_id?: string | null;
  amount: string;
  total_amount?: string | null;
  currency: string;
  status: string;
  match_status: string;
  created_at: string;
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
  status?: string;
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

export interface WorkflowFieldSpec {
  path: string;
  label: string;
  type: string;
}

export interface WorkflowFieldListResponse {
  entity_type: string;
  fields: WorkflowFieldSpec[];
}

// Mirrors APPROVER_ROLE_CODES in backend/app/models/approval.py -- keep in sync.
export const APPROVER_ROLE_CODES = [
  "MANAGER",
  "MANAGER_MANAGER",
  "DEPT_HEAD",
  "CFO",
  "FIN_CTRL",
  "PROC_HEAD",
  "AP_HEAD",
  "AP_PROCESSOR",
] as const;

export type ApproverRoleCode = (typeof APPROVER_ROLE_CODES)[number];

export interface ResolvedApprover {
  user_id: string;
  display_name: string;
  email: string;
  role_code: string;
  is_primary_approver: boolean;
  backup_approver_user_id?: string | null;
  org_unit_id?: string | null;
  reason: string;
}

export interface ResolveApproversResponse {
  role_code: string;
  approvers: ResolvedApprover[];
  count: number;
}

// Shapes match backend/app/routers/approval.py's _seed_to_dict (there is no
// backend/app/schemas/approval.py -- the router serializes the model directly).
export interface ApproverSeed {
  id: string;
  user_id: string;
  display_name: string;
  email: string;
  role_code: string;
  org_unit_id?: string | null;
  approval_limit_currency?: string | null;
  approval_limit_amount?: string | null;
  category_scope?: string | null;
  supplier_scope?: string | null;
  is_primary_approver: boolean;
  backup_approver_user_id?: string | null;
  delegation_start_date?: string | null;
  delegation_end_date?: string | null;
  active_flag: boolean;
}

export interface ApproverSeedUpsert {
  user_id: string;
  display_name?: string;
  email?: string;
  role_code: string;
  org_unit_id?: string | null;
  approval_limit_currency?: string | null;
  approval_limit_amount?: string | null;
  category_scope?: string | null;
  supplier_scope?: string | null;
  is_primary_approver?: boolean;
  backup_approver_user_id?: string | null;
  delegation_start_date?: string | null;
  delegation_end_date?: string | null;
  active_flag?: boolean;
}

export interface SlaDefinitionEntry {
  id: string;
  document_type: string;
  node_type?: string | null;
  role_code?: string | null;
  target_duration_minutes: number;
  severity: string;
}

export interface ApprovalAnalytics {
  avg_approval_time_by_type: Array<{ node: string; avg_approval_hours: number; count: number }>;
  sla_breach_rate_by_node: Array<{ node: string; breach_rate: number; total: number }>;
  total_sla_metrics: number;
  total_sla_breaches: number;
}

export interface ProcurementAuditEvent {
  id: string;
  requisition_id: string;
  actor_id: string;
  action: string;
  details?: Record<string, unknown> | null;
  created_at: string;
}

export interface ProcurementComment {
  id: string;
  requisition_id?: string | null;
  purchase_order_id?: string | null;
  author_id: string;
  comment: string;
  created_at: string;
}

export interface PurchaseOrderVersion {
  id: string;
  purchase_order_id: string;
  version_number: number;
  change_type: string;
  changes?: Record<string, unknown> | null;
  created_by: string;
  created_at: string;
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
