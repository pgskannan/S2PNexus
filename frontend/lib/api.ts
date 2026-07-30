import axios, { AxiosError } from "axios";
import { useAuthStore } from "@/lib/auth-store";
import type {
  AccountingSplit,
  AddressResult,
  AgentQueryResponse,
  AgentActivityLogEntry,
  AgentActivityLogListResponse,
  AgentActivitySummaryResponse,
  CommodityCodeResult,
  Contract,
  DocumentNumberingFormat,
  DocumentNumberingFormatListResponse,
  DocumentNumberingPreviewResponse,
  DocumentType,
  ResetCadence,
  ContractListResponse,
  Document,
  DocumentListResponse,
  PurchaseOrder,
  PurchaseOrderListResponse,
  Requisition,
  RequisitionListResponse,
  RequisitionLineItem,
  SavingsListResponse,
  SavingsSummaryResponse,
  SourcingEvent,
  SourcingEventListResponse,
  SpendAnalyticsResponse,
  Supplier,
  SupplierListResponse,
  SupplierHierarchyResponse,
  SupplierSpendRollupResponse,
  SupplierDuplicatesResponse,
  Token,
  User,
  WorkflowDefinition,
  WorkflowDefinitionListResponse,
  WorkflowInstance,
  WorkflowInstanceListResponse,
  WorkflowTask,
  Notification,
  NotificationListResponse,
  DashboardMetricsResponse,
  AiProviderResponse,
  UserListResponse,
  UserUpdate,
  Budget,
  BudgetCreate,
  BudgetUpdate,
  BudgetCheckResponse,
  BudgetListResponse,
} from "@/lib/types";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

export const api = axios.create({
  baseURL: API_BASE_URL,
});

api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().accessToken;
  if (token) {
    config.headers = config.headers ?? {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response?.status === 401) {
      useAuthStore.getState().logout();
      if (typeof window !== "undefined") {
        window.location.href = "/login";
      }
    }
    return Promise.reject(error);
  }
);

export function extractErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = (error.response?.data as { detail?: unknown })?.detail;
    if (typeof detail === "string") return detail;
    if (detail) return JSON.stringify(detail);
    return error.message;
  }
  return error instanceof Error ? error.message : "Unexpected error";
}

// ---- Auth ----

export async function login(email: string, password: string): Promise<Token> {
  const form = new URLSearchParams();
  form.set("username", email);
  form.set("password", password);
  const { data } = await axios.post<Token>(
    `${API_BASE_URL}/auth/login`,
    form,
    { headers: { "Content-Type": "application/x-www-form-urlencoded" } }
  );
  return data;
}

export async function register(payload: {
  email: string;
  full_name: string;
  password: string;
  role: string;
}): Promise<User> {
  const { data } = await axios.post<User>(
    `${API_BASE_URL}/auth/register`,
    payload
  );
  return data;
}

export async function getMe(token: string): Promise<User> {
  const { data } = await axios.get<User>(`${API_BASE_URL}/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  return data;
}

// ---- Procurement (Requisitions) ----

export async function listRequisitions(params?: {
  search?: string;
  status?: string;
  category?: string;
  supplier_id?: string;
  created_after?: string;
  created_before?: string;
  priority?: string;
  estimated_value_min?: number;
  estimated_value_max?: number;
  requested_by?: string;
  limit?: number;
  skip?: number;
}): Promise<RequisitionListResponse> {
  const { data } = await api.get<RequisitionListResponse>(
    "/procurement/requisitions",
    { params }
  );
  return data;
}

export async function getRequisition(id: string): Promise<Requisition> {
  const { data } = await api.get<Requisition>(
    `/procurement/requisitions/${id}`
  );
  return data;
}

export async function createRequisition(
  payload: Partial<Requisition> & { title: string; requested_by: string }
): Promise<Requisition> {
  const { data } = await api.post<Requisition>(
    "/procurement/requisitions",
    payload
  );
  return data;
}

export async function transitionRequisition(
  id: string,
  newStatus: string,
  lifecycleStatus: string
): Promise<Requisition> {
  const { data } = await api.post<Requisition>(
    `/procurement/requisitions/${id}/transition`,
    { new_status: newStatus, lifecycle_status: lifecycleStatus }
  );
  return data;
}

export async function deleteRequisition(id: string): Promise<void> {
  await api.delete(`/procurement/requisitions/${id}`);
}

export async function addRequisitionLineItem(
  requisitionId: string,
  payload: {
    description: string;
    quantity: string;
    unit_price?: string;
    line_total?: string;
    commodity?: string;
    category?: string;
    account_code?: string;
  }
): Promise<RequisitionLineItem> {
  const { data } = await api.post<RequisitionLineItem>(
    `/procurement/requisitions/${requisitionId}/line-items`,
    payload
  );
  return data;
}

// ---- Commodity codes (autocomplete) ----

export async function searchCommodityCodes(
  search?: string
): Promise<CommodityCodeResult[]> {
  const { data } = await api.get<CommodityCodeResult[]>("/commodity-codes", {
    params: search ? { search } : undefined,
  });
  return data;
}

export async function searchCategories(
  search?: string
): Promise<Array<{ code: string; name?: string | null; is_active: boolean }>> {
  const { data } = await api.get<Array<{ code: string; name?: string | null; is_active: boolean }>>(
    "/categories",
    { params: search ? { search } : undefined }
  );
  return data;
}

// ---- Addresses (ship-to / bill-to picker) ----

export async function listMyAddresses(): Promise<AddressResult[]> {
  // /addresses/mine already returns both the caller's own addresses and their
  // tenant's shared addresses (see app/routers/address.py) -- one call covers
  // the full picker list.
  const { data } = await api.get<AddressResult[]>("/addresses/mine");
  return data;
}

// ---- Admin / Users ----

export interface UserDirectoryEntry {
  id: string;
  full_name: string;
  email: string;
}

// Unlike listUsers()/getUser() below (admin-only, 403s for non-superusers),
// this hits GET /users/directory -- available to any authenticated user, for
// resolving a requested_by/assignee_id UUID to a display name (requisition
// lists, the Ariba-style approval flow diagram, etc). Deliberately returns
// only id/full_name/email, nothing sensitive.
export async function listUserDirectory(params?: { limit?: number }): Promise<{ items: UserDirectoryEntry[] }> {
  const { data } = await api.get<{ items: UserDirectoryEntry[] }>("/users/directory", { params });
  return data;
}

export async function listUsers(params?: {
  skip?: number;
  limit?: number;
  search?: string;
  sort_by?: string;
  sort_order?: string;
}): Promise<UserListResponse> {
  const { data } = await api.get<UserListResponse>("/users", { params });
  return data;
}

export async function getUser(id: string): Promise<User> {
  const { data } = await api.get<User>(`/users/${id}`);
  return data;
}

export async function updateUser(id: string, payload: UserUpdate): Promise<User> {
  const { data } = await api.patch<User>(`/users/${id}`, payload);
  return data;
}

export async function deleteUser(id: string): Promise<void> {
  await api.delete(`/users/${id}`);
}

// ---- Admin / Budgets ----

export async function listBudgets(params?: { fiscal_year?: number }): Promise<BudgetListResponse> {
  const { data } = await api.get<BudgetListResponse>("/budgets", { params });
  return data;
}

export async function createBudget(payload: BudgetCreate): Promise<Budget> {
  const { data } = await api.post<Budget>("/budgets", payload);
  return data;
}

export async function getBudget(id: string): Promise<Budget> {
  const { data } = await api.get<Budget>(`/budgets/${id}`);
  return data;
}

export async function updateBudget(id: string, payload: BudgetUpdate): Promise<Budget> {
  const { data } = await api.put<Budget>(`/budgets/${id}`, payload);
  return data;
}

export async function checkBudget(params: {
  requested_amount: number | string;
  gl_account_code?: string;
  cost_center?: string;
  fiscal_year?: number;
  fiscal_period?: number;
}): Promise<BudgetCheckResponse> {
  const { data } = await api.get<BudgetCheckResponse>("/budgets/check", { params });
  return data;
}

// ---- Admin / Shared addresses ----

export async function listSharedAddresses(): Promise<AddressResult[]> {
  const { data } = await api.get<AddressResult[]>("/addresses/shared");
  return data;
}

export async function createSharedAddress(payload: Record<string, unknown>): Promise<{ id: string }> {
  const { data } = await api.post<{ id: string }>("/addresses/shared", payload);
  return data;
}

export async function updateSharedAddress(id: string, payload: Record<string, unknown>): Promise<{ id: string }> {
  const { data } = await api.patch<{ id: string }>(`/addresses/shared/${id}`, payload);
  return data;
}

export async function deleteSharedAddress(id: string): Promise<{ deleted: boolean }> {
  const { data } = await api.delete<{ deleted: boolean }>(`/addresses/shared/${id}`);
  return data;
}

// ---- Purchase Orders ----

export async function listPurchaseOrders(params?: {
  requisition_id?: string;
  status?: string;
  skip?: number;
  limit?: number;
}): Promise<PurchaseOrderListResponse> {
  const { data } = await api.get<PurchaseOrderListResponse>(
    "/procurement/purchase-orders",
    { params }
  );
  return data;
}

export async function getPurchaseOrder(id: string): Promise<PurchaseOrder> {
  const { data } = await api.get<PurchaseOrder>(
    `/procurement/purchase-orders/${id}`
  );
  return data;
}

export async function convertRequisitionToPurchaseOrder(
  requisitionId: string,
  payload: {
    supplier_id: string;
    currency?: string;
    notes?: string;
    line_items?: Array<Record<string, unknown>>;
    shipping_amount?: string;
    shipping_allocation_method?: string;
    ship_to_address_id?: string;
    bill_to_address_id?: string;
    incoterms?: string;
    payment_terms?: string;
  }
): Promise<PurchaseOrder> {
  const { data } = await api.post<PurchaseOrder>(
    `/procurement/requisitions/${requisitionId}/convert-to-po`,
    payload
  );
  return data;
}

export async function transitionPurchaseOrderLifecycle(
  id: string,
  lifecycleStatus: string
): Promise<PurchaseOrder> {
  const { data } = await api.post<PurchaseOrder>(
    `/procurement/purchase-orders/${id}/lifecycle/transition`,
    { lifecycle_status: lifecycleStatus }
  );
  return data;
}

export async function acknowledgePurchaseOrder(
  id: string,
  notes?: string
): Promise<PurchaseOrder> {
  const { data } = await api.post<PurchaseOrder>(
    `/procurement/purchase-orders/${id}/acknowledge`,
    { notes }
  );
  return data;
}

export async function getPurchaseOrderLineItemSplits(
  purchaseOrderId: string,
  lineItemId: string
): Promise<AccountingSplit[]> {
  const { data } = await api.get<AccountingSplit[]>(
    `/procurement/purchase-orders/${purchaseOrderId}/line-items/${lineItemId}/splits`
  );
  return data;
}

export async function setPurchaseOrderLineItemSplits(
  purchaseOrderId: string,
  lineItemId: string,
  splits: Array<{
    split_method: "percentage" | "amount";
    percentage?: string;
    amount?: string;
    gl_account_code: string;
    cost_center?: string;
    department?: string;
    project_code?: string;
  }>
): Promise<AccountingSplit[]> {
  const { data } = await api.put<AccountingSplit[]>(
    `/procurement/purchase-orders/${purchaseOrderId}/line-items/${lineItemId}/splits`,
    { splits }
  );
  return data;
}

// ---- Suppliers ----

export async function listSuppliers(params?: {
  search?: string;
}): Promise<SupplierListResponse> {
  const { data } = await api.get<SupplierListResponse>("/suppliers", {
    params,
  });
  return data;
}

export async function createSupplier(payload: {
  name: string;
  contact_email?: string;
  contact_phone?: string;
  address?: string;
  website?: string;
  payment_terms?: string;
  currency?: string;
}): Promise<Supplier> {
  const { data } = await api.post<Supplier>("/suppliers", payload);
  return data;
}

export async function getSupplier(id: string): Promise<Supplier> {
  const { data } = await api.get<Supplier>(`/suppliers/${id}`);
  return data;
}

// -- Supplier lifecycle (continuous monitoring / requalification / offboarding) --

export async function transitionSupplierLifecycle(
  id: string,
  payload: {
    action: string;
    reason?: string;
    next_requalification_due_at?: string;
  }
): Promise<Supplier> {
  const { data } = await api.post<Supplier>(
    `/suppliers/${id}/lifecycle/transition`,
    payload
  );
  return data;
}

// -- Supplier hierarchy --

export async function getSupplierHierarchy(
  id: string
): Promise<SupplierHierarchyResponse> {
  const { data } = await api.get<SupplierHierarchyResponse>(
    `/suppliers/${id}/hierarchy`
  );
  return data;
}

export async function updateSupplierHierarchy(
  id: string,
  payload: { parent_supplier_id: string | null; relationship_type?: string }
): Promise<Supplier> {
  const { data } = await api.patch<Supplier>(
    `/suppliers/${id}/hierarchy`,
    payload
  );
  return data;
}

export async function getSupplierSpendRollup(
  id: string
): Promise<SupplierSpendRollupResponse> {
  const { data } = await api.get<SupplierSpendRollupResponse>(
    `/suppliers/${id}/spend-rollup`
  );
  return data;
}

// -- Duplicate management --

export async function getSupplierDuplicates(
  id: string,
  params?: { min_score?: number; limit?: number }
): Promise<SupplierDuplicatesResponse> {
  const { data } = await api.get<SupplierDuplicatesResponse>(
    `/suppliers/${id}/duplicates`,
    { params }
  );
  return data;
}

export async function mergeSuppliers(payload: {
  source_supplier_id: string;
  target_supplier_id: string;
}): Promise<Supplier> {
  const { data } = await api.post<Supplier>("/suppliers/merge", payload);
  return data;
}

// ---- Contracts ----

export async function listContracts(params?: {
  search?: string;
  status?: string;
}): Promise<ContractListResponse> {
  const { data } = await api.get<ContractListResponse>("/contracts", {
    params,
  });
  return data;
}

export async function getContract(id: string): Promise<Contract> {
  const { data } = await api.get<Contract>(`/contracts/${id}`);
  return data;
}

export async function listDocuments(params?: {
  search?: string;
  document_type?: string;
}): Promise<DocumentListResponse> {
  const { data } = await api.get<DocumentListResponse>("/documents", {
    params,
  });
  return data;
}

export async function uploadDocument(
  file: File,
  document_type?: string
): Promise<Document> {
  // The backend endpoint declares `document_type` as a plain parameter
  // alongside `file: UploadFile = File(...)` with no `Form(...)` annotation,
  // so FastAPI parses it as a query parameter, not a multipart form field --
  // sending it in the FormData body gets silently ignored (always falls
  // back to the "general" default).
  const formData = new FormData();
  formData.append("file", file);
  const { data } = await api.post<Document>("/documents/upload", formData, {
    headers: { "Content-Type": "multipart/form-data" },
    params: document_type ? { document_type } : undefined,
  });
  return data;
}

export async function deleteDocument(id: string): Promise<void> {
  await api.delete(`/documents/${id}`);
}

export async function createContract(payload: Partial<Contract> & {
  title: string;
  contract_number: string;
  supplier_id: string;
  contract_type: string;
  start_date: string;
}): Promise<Contract> {
  const { data } = await api.post<Contract>("/contracts", payload);
  return data;
}

// ---- Sourcing ----

export async function listSourcingEvents(params?: {
  search?: string;
  status?: string;
  event_type?: string;
}): Promise<SourcingEventListResponse> {
  // Note: the sourcing router is mounted at the full "/sourcing" prefix in
  // main.py (its own APIRouter declares prefix=""), unlike contracts/
  // procurement/suppliers which declare their own prefix and only need the
  // bare "/api/v1" supplied externally. Actual path: /api/v1/sourcing/events.
  const { data } = await api.get<SourcingEventListResponse>(
    "/sourcing/events",
    { params }
  );
  return data;
}

export async function getSourcingEvent(id: string): Promise<SourcingEvent> {
  const { data } = await api.get<SourcingEvent>(`/sourcing/events/${id}`);
  return data;
}

export async function createSourcingEvent(payload: {
  event_number: string;
  title: string;
  description?: string;
  event_type: string;
  category?: string;
  owner_id: string;
  currency?: string;
  estimated_value?: string;
  start_date?: string;
  response_due_date?: string;
  status?: string;
  lifecycle_status?: string;
}): Promise<SourcingEvent> {
  const { data } = await api.post<SourcingEvent>(
    "/sourcing/events",
    payload
  );
  return data;
}

// ---- Workflow ----

export async function listWorkflowDefinitions(params?: {
  entity_type?: string;
  is_active?: boolean;
}): Promise<WorkflowDefinitionListResponse> {
  const { data } = await api.get<WorkflowDefinitionListResponse>(
    "/workflow/definitions",
    { params }
  );
  return data;
}

export async function createWorkflowDefinition(payload: {
  name: string;
  entity_type: string;
  description?: string;
  steps: Array<Record<string, unknown>>;
  is_active?: boolean;
}): Promise<WorkflowDefinition> {
  const { data } = await api.post<WorkflowDefinition>(
    "/workflow/definitions",
    payload
  );
  return data;
}

export async function getWorkflowDefinition(id: string): Promise<WorkflowDefinition> {
  const { data } = await api.get<WorkflowDefinition>(`/workflow/definitions/${id}`);
  return data;
}

export async function listWorkflowInstances(params?: {
  entity_type?: string;
  entity_id?: string;
  status?: string;
}): Promise<WorkflowInstanceListResponse> {
  const { data } = await api.get<WorkflowInstanceListResponse>(
    "/workflow/instances",
    { params }
  );
  return data;
}

export async function getWorkflowInstance(id: string): Promise<WorkflowInstance> {
  const { data } = await api.get<WorkflowInstance>(`/workflow/instances/${id}`);
  return data;
}

export async function listMyWorkflowTasks(params?: {
  status?: string;
}): Promise<WorkflowTask[]> {
  const { data } = await api.get<WorkflowTask[]>("/workflow/tasks/my", {
    params,
  });
  return data;
}

export async function completeWorkflowTask(
  id: string,
  payload: { decision: "approve" | "reject"; comments?: string }
): Promise<WorkflowTask> {
  const { data } = await api.post<WorkflowTask>(
    `/workflow/tasks/${id}/complete`,
    payload
  );
  return data;
}

export async function listWorkflowNotifications(params?: {
  unread_only?: boolean;
  skip?: number;
  limit?: number;
}): Promise<NotificationListResponse> {
  const { data } = await api.get<NotificationListResponse>(
    "/workflow/notifications",
    { params }
  );
  return data;
}

export async function markWorkflowNotificationRead(
  id: string
): Promise<Notification> {
  const { data } = await api.post<Notification>(
    `/workflow/notifications/${id}/read`
  );
  return data;
}

// ---- Analytics ----

export async function getDashboardMetrics(): Promise<DashboardMetricsResponse> {
  const { data } = await api.get<DashboardMetricsResponse>("/analytics/dashboard");
  return data;
}

export async function getSpendAnalytics(params?: {
  start_date?: string;
  end_date?: string;
  category?: string;
  supplier_id?: string;
}): Promise<SpendAnalyticsResponse> {
  const { data } = await api.get<SpendAnalyticsResponse>("/analytics/spend", {
    params,
  });
  return data;
}

export async function getSavingsSummary(): Promise<SavingsSummaryResponse> {
  // GET /analytics/savings returns a full SavingsListResponse (items/total/
  // skip/limit/summary), not a bare summary object -- the summary rollup is
  // nested under `.summary`. Unwrap it here so callers keep getting just the
  // summary shape.
  const { data } = await api.get<SavingsListResponse>("/analytics/savings");
  return data.summary;
}

// ---- AI Provider ----

export async function getAiProvider(): Promise<AiProviderResponse> {
  const { data } = await api.get<AiProviderResponse>("/ai/provider");
  return data;
}

export async function updateAiProvider(provider: string): Promise<AiProviderResponse> {
  const { data } = await api.put<AiProviderResponse>("/ai/provider", { provider });
  return data;
}

// ---- AI Agents ----

export async function queryAgent(
  request: string
): Promise<AgentQueryResponse> {
  const { data } = await api.post<AgentQueryResponse>("/ai/agents/query", {
    request,
    metadata: {},
  });
  return data;
}

// ---- Agent Activity (read-only audit trail / dashboard) ----

export async function listAgentActivity(params?: {
  agent_name?: string;
  success?: boolean;
  limit?: number;
  offset?: number;
}): Promise<AgentActivityLogListResponse> {
  const { data } = await api.get<AgentActivityLogListResponse>(
    "/ai/agents/activity",
    { params }
  );
  return data;
}

export async function getAgentActivitySummary(): Promise<AgentActivitySummaryResponse> {
  const { data } = await api.get<AgentActivitySummaryResponse>(
    "/ai/agents/activity/summary"
  );
  return data;
}

export async function getAgentActivityDetail(
  id: string
): Promise<AgentActivityLogEntry> {
  const { data } = await api.get<AgentActivityLogEntry>(
    `/ai/agents/activity/${id}`
  );
  return data;
}

// ---- Document Numbering (tenant-admin configurable PR/PO/Receipt/Invoice numbers) ----

export async function listDocumentNumberingFormats(): Promise<DocumentNumberingFormatListResponse> {
  const { data } = await api.get<DocumentNumberingFormatListResponse>(
    "/document-numbering"
  );
  return data;
}

export async function updateDocumentNumberingFormat(
  documentType: DocumentType,
  payload: {
    prefix: string;
    pattern: string;
    sequence_padding: number;
    reset_cadence: ResetCadence;
  }
): Promise<DocumentNumberingFormat> {
  const { data } = await api.put<DocumentNumberingFormat>(
    `/document-numbering/${documentType}`,
    payload
  );
  return data;
}

export async function previewDocumentNumberingFormat(payload: {
  document_type: DocumentType;
  prefix: string;
  pattern: string;
  sequence_padding: number;
  reset_cadence: ResetCadence;
}): Promise<DocumentNumberingPreviewResponse> {
  const { data } = await api.post<DocumentNumberingPreviewResponse>(
    "/document-numbering/preview",
    payload
  );
  return data;
}

// ---- Master data: commodity codes, GL accounts, commodity-to-GL mapping ----
// Three independent datasets, same shape of admin-only upload/delete-all/count
// endpoints. GL accounts should be loaded before mapping (mapping upload
// validates gl_account_code against the GL accounts already loaded).

async function uploadCsv<T = { loaded: number }>(path: string, file: File): Promise<T> {
  const formData = new FormData();
  formData.append("file", file);
  const { data } = await api.post<T>(path, formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

// Fetches a CSV export as a blob (auth header goes through the same axios
// interceptor as every other call, so this can't be a plain <a href> link)
// and triggers a browser download via a throwaway anchor element.
async function downloadCsv(path: string, filename: string): Promise<void> {
  const response = await api.get(path, { responseType: "blob" });
  const url = window.URL.createObjectURL(new Blob([response.data]));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}

export async function getCommodityCodeCount(): Promise<{ count: number }> {
  const { data } = await api.get<{ count: number }>("/commodity-codes/master-data/count");
  return data;
}

export async function uploadCommodityCodes(file: File): Promise<{ loaded: number }> {
  return uploadCsv("/commodity-codes/master-data/upload", file);
}

export async function downloadCommodityCodes(): Promise<void> {
  return downloadCsv("/commodity-codes/master-data/export", "commodity_codes.csv");
}

export async function deleteAllCommodityCodes(): Promise<{ deleted: number }> {
  const { data } = await api.delete<{ deleted: number }>("/commodity-codes/master-data");
  return data;
}

export async function getGlAccountCount(): Promise<{ count: number }> {
  const { data } = await api.get<{ count: number }>("/gl-accounts/count");
  return data;
}

export async function uploadGlAccounts(file: File): Promise<{ loaded: number }> {
  return uploadCsv("/gl-accounts/upload", file);
}

export async function downloadGlAccounts(): Promise<void> {
  return downloadCsv("/gl-accounts/export", "gl_accounts.csv");
}

export async function deleteAllGlAccounts(): Promise<{ deleted: number }> {
  const { data } = await api.delete<{ deleted: number }>("/gl-accounts");
  return data;
}

export async function getCommodityGlMappingCount(): Promise<number> {
  const { data } = await api.get<unknown[]>("/commodity-codes/mappings");
  return data.length;
}

export async function uploadCommodityGlMapping(file: File): Promise<{ loaded: number; errors: string[] }> {
  return uploadCsv<{ loaded: number; errors: string[] }>("/commodity-codes/mappings/upload", file);
}

export async function downloadCommodityGlMapping(): Promise<void> {
  return downloadCsv("/commodity-codes/mappings/export", "commodity_gl_mapping.csv");
}

export async function getDepartmentsCount(): Promise<{ count: number }> {
  const { data } = await api.get<{ count: number }>("/departments/master-data/count");
  return data;
}

export async function uploadDepartments(file: File): Promise<{ loaded: number; errors?: string[] }> {
  return uploadCsv<{ loaded: number; errors?: string[] }>("/departments/master-data/upload", file);
}

export async function downloadDepartments(): Promise<void> {
  return downloadCsv("/departments/master-data/export", "departments.csv");
}

export async function deleteAllDepartments(): Promise<{ deleted: number }> {
  const { data } = await api.delete<{ deleted: number }>("/departments/master-data");
  return data;
}

export async function getCostCentersCount(): Promise<{ count: number }> {
  const { data } = await api.get<{ count: number }>("/cost-centers/master-data/count");
  return data;
}

export async function uploadCostCenters(file: File): Promise<{ loaded: number; errors?: string[] }> {
  return uploadCsv<{ loaded: number; errors?: string[] }>("/cost-centers/master-data/upload", file);
}

export async function downloadCostCenters(): Promise<void> {
  return downloadCsv("/cost-centers/master-data/export", "cost_centers.csv");
}

export async function deleteAllCostCenters(): Promise<{ deleted: number }> {
  const { data } = await api.delete<{ deleted: number }>("/cost-centers/master-data");
  return data;
}

export async function getPlantsCount(): Promise<{ count: number }> {
  const { data } = await api.get<{ count: number }>("/plants/master-data/count");
  return data;
}

export async function uploadPlants(file: File): Promise<{ loaded: number; errors?: string[] }> {
  return uploadCsv<{ loaded: number; errors?: string[] }>("/plants/master-data/upload", file);
}

export async function downloadPlants(): Promise<void> {
  return downloadCsv("/plants/master-data/export", "plants.csv");
}

export async function deleteAllPlants(): Promise<{ deleted: number }> {
  const { data } = await api.delete<{ deleted: number }>("/plants/master-data");
  return data;
}

export async function deleteAllCommodityGlMapping(): Promise<{ deleted: number }> {
  const { data } = await api.delete<{ deleted: number }>("/commodity-codes/mappings");
  return data;
}
