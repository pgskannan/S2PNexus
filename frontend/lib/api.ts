import axios, { AxiosError } from "axios";
import { useAuthStore } from "@/lib/auth-store";
import type {
  AccountingSplit,
  ActAsSessionListResponse,
  ActAsSessionResponse,
  ActAsStartResponse,
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
  WorkflowFieldListResponse,
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
      const store = useAuthStore.getState();
      if (store.originalSession) {
        // The impersonation token 401'd (expired after 30 min, or was
        // ended server-side) -- fall back to the admin's own stashed
        // session instead of a full logout, so a lapsed "Act as" doesn't
        // force the admin to re-authenticate.
        store.endActAs();
        if (typeof window !== "undefined") {
          window.location.href = "/dashboard";
        }
      } else {
        store.logout();
        if (typeof window !== "undefined") {
          window.location.href = "/login";
        }
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
  approval_status?: string;
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

export async function listRequisitionAuditEvents(id: string): Promise<import("@/lib/types").ProcurementAuditEvent[]> {
  const { data } = await api.get<import("@/lib/types").ProcurementAuditEvent[]>(
    `/procurement/requisitions/${id}/audit-events`
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

export async function getRequisitionApprovalPreview(
  id: string
): Promise<import("@/lib/types").RequisitionApprovalPreview> {
  const { data } = await api.get<import("@/lib/types").RequisitionApprovalPreview>(
    `/procurement/requisitions/${id}/approval-preview`
  );
  return data;
}

export async function previewRequisitionApproval(payload: {
  estimated_value?: string | null;
  priority?: string | null;
  category?: string | null;
  account_code?: string | null;
  commodity?: string | null;
  supplier_id?: string | null;
  currency?: string | null;
  is_emergency?: boolean;
  // Real line-item total drives auto-approve/threshold conditions -- send
  // these so the preview reflects the actual computed cost, not just the
  // free-typed estimated_value field (see compute_line_items_total_cost).
  line_items?: { quantity: string; unit_price?: string | null }[];
  header_tax?: string | null;
  shipping_cost?: string | null;
}): Promise<import("@/lib/types").RequisitionApprovalPreview> {
  const { data } = await api.post<import("@/lib/types").RequisitionApprovalPreview>(
    `/procurement/requisitions/approval-preview`,
    payload
  );
  return data;
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
export async function listUserDirectory(params?: { limit?: number; search?: string }): Promise<{ items: UserDirectoryEntry[] }> {
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

// ---- Admin / Act as User (impersonation) ----

export async function startActAsSession(targetUserId: string): Promise<ActAsStartResponse> {
  const { data } = await api.post<ActAsStartResponse>("/admin/act-as/sessions", {
    target_user_id: targetUserId,
  });
  return data;
}

export async function endActAsSessionRequest(sessionId: string): Promise<ActAsSessionResponse> {
  const { data } = await api.post<ActAsSessionResponse>(`/admin/act-as/sessions/${sessionId}/end`);
  return data;
}

export async function listActAsSessions(params?: {
  admin_user_id?: string;
  target_user_id?: string;
  active_only?: boolean;
  skip?: number;
  limit?: number;
}): Promise<ActAsSessionListResponse> {
  const { data } = await api.get<ActAsSessionListResponse>("/admin/act-as/sessions", { params });
  return data;
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

export async function listGoodsReceipts(): Promise<{ items: import("@/lib/types").GoodsReceipt[] }> {
  const { data } = await api.get<{ items: import("@/lib/types").GoodsReceipt[] }>("/procurement/receipts");
  return data;
}

export async function getGoodsReceipt(id: string): Promise<import("@/lib/types").GoodsReceipt> {
  const { data } = await api.get<import("@/lib/types").GoodsReceipt>(`/procurement/receipts/${id}`);
  return data;
}

export interface GoodsReceiptLineItemCreate {
  purchase_order_line_item_id: string;
  quantity_received: string | number;
  quantity_rejected?: string | number;
  rejection_reason?: string | null;
  condition_status?: string;
  notes?: string | null;
}

export interface GoodsReceiptCreate {
  status?: string;
  receipt_type?: string;
  inspection_status?: string;
  carrier?: string | null;
  tracking_number?: string | null;
  delivery_note_reference?: string | null;
  notes?: string | null;
  line_items: GoodsReceiptLineItemCreate[];
}

export async function createGoodsReceipt(
  purchaseOrderId: string,
  payload: GoodsReceiptCreate
): Promise<import("@/lib/types").GoodsReceipt> {
  const { data } = await api.post<import("@/lib/types").GoodsReceipt>(
    `/procurement/purchase-orders/${purchaseOrderId}/receipts`,
    payload
  );
  return data;
}

export async function submitGoodsReceipt(receiptId: string): Promise<import("@/lib/types").GoodsReceipt> {
  const { data } = await api.post<import("@/lib/types").GoodsReceipt>(`/procurement/receipts/${receiptId}/submit`);
  return data;
}

export async function approveGoodsReceipt(receiptId: string): Promise<import("@/lib/types").GoodsReceipt> {
  const { data } = await api.post<import("@/lib/types").GoodsReceipt>(`/procurement/receipts/${receiptId}/approve`);
  return data;
}

export async function postGoodsReceipt(receiptId: string): Promise<import("@/lib/types").GoodsReceipt> {
  const { data } = await api.post<import("@/lib/types").GoodsReceipt>(`/procurement/receipts/${receiptId}/post`);
  return data;
}

export async function rejectGoodsReceipt(
  receiptId: string,
  reason: string
): Promise<import("@/lib/types").GoodsReceipt> {
  const { data } = await api.post<import("@/lib/types").GoodsReceipt>(`/procurement/receipts/${receiptId}/reject`, {
    reason,
  });
  return data;
}

export async function inspectGoodsReceipt(
  receiptId: string,
  inspectionStatus: "passed" | "failed"
): Promise<import("@/lib/types").GoodsReceipt> {
  const { data } = await api.post<import("@/lib/types").GoodsReceipt>(`/procurement/receipts/${receiptId}/inspect`, {
    inspection_status: inspectionStatus,
  });
  return data;
}

export async function getPurchaseOrderGrir(
  purchaseOrderId: string
): Promise<import("@/lib/types").GrirRecord[]> {
  const { data } = await api.get<import("@/lib/types").GrirRecord[]>(
    `/procurement/purchase-orders/${purchaseOrderId}/grir`
  );
  return data;
}

export async function listInvoices(): Promise<{ items: import("@/lib/types").ProcurementInvoice[] }> {
  const { data } = await api.get<{ items: import("@/lib/types").ProcurementInvoice[] }>("/procurement/invoices");
  return data;
}

export interface InvoiceLineItemCreate {
  purchase_order_line_item_id?: string | null;
  description: string;
  quantity?: string | number;
  unit_price?: string | number | null;
  line_total?: string | number | null;
  tax_amount?: string | number | null;
}

export interface InvoiceCreate {
  supplier_id?: string | null;
  purchase_order_id?: string | null;
  amount: string | number;
  tax_amount?: string | number | null;
  total_amount?: string | number | null;
  currency?: string;
  description?: string | null;
  line_items?: InvoiceLineItemCreate[] | null;
}

export async function createInvoice(payload: InvoiceCreate): Promise<import("@/lib/types").ProcurementInvoice> {
  const { data } = await api.post<import("@/lib/types").ProcurementInvoice>("/procurement/invoices", payload);
  return data;
}

export async function listRequisitionComments(id: string): Promise<import("@/lib/types").ProcurementComment[]> {
  const { data } = await api.get<import("@/lib/types").ProcurementComment[]>(`/procurement/requisitions/${id}/comments`);
  return data;
}

export async function addRequisitionComment(id: string, comment: string): Promise<import("@/lib/types").ProcurementComment> {
  const { data } = await api.post<import("@/lib/types").ProcurementComment>(`/procurement/requisitions/${id}/comments`, { comment });
  return data;
}

export async function listPurchaseOrderComments(id: string): Promise<import("@/lib/types").ProcurementComment[]> {
  const { data } = await api.get<import("@/lib/types").ProcurementComment[]>(`/procurement/purchase-orders/${id}/comments`);
  return data;
}

export async function addPurchaseOrderComment(id: string, comment: string): Promise<import("@/lib/types").ProcurementComment> {
  const { data } = await api.post<import("@/lib/types").ProcurementComment>(`/procurement/purchase-orders/${id}/comments`, { comment });
  return data;
}

export async function getPurchaseOrderVersions(id: string): Promise<import("@/lib/types").PurchaseOrderVersion[]> {
  const { data } = await api.get<import("@/lib/types").PurchaseOrderVersion[]>(`/procurement/purchase-orders/${id}/versions`);
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

export async function listWorkflowFields(entityType: string): Promise<WorkflowFieldListResponse> {
  const { data } = await api.get<WorkflowFieldListResponse>("/workflow/fields", {
    params: { entity_type: entityType },
  });
  return data;
}

export async function updateWorkflowDefinition(
  id: string,
  payload: {
    name: string;
    entity_type: string;
    description?: string;
    steps: Array<Record<string, unknown>>;
    is_active?: boolean;
  }
): Promise<WorkflowDefinition> {
  const { data } = await api.put<WorkflowDefinition>(`/workflow/definitions/${id}`, payload);
  return data;
}

export async function deleteWorkflowDefinition(id: string): Promise<void> {
  await api.delete(`/workflow/definitions/${id}`);
}

export async function listWorkflowInstances(params?: {
  entity_type?: string;
  entity_id?: string;
  status?: string;
  skip?: number;
  limit?: number;
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

export async function retryWorkflowInstance(id: string): Promise<WorkflowInstance> {
  const { data } = await api.post<WorkflowInstance>(`/workflow/instances/${id}/retry`);
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

export async function adminRemoveWorkflowTask(id: string, reason?: string): Promise<WorkflowTask> {
  const { data } = await api.post<WorkflowTask>(`/workflow/tasks/${id}/admin-remove`, { reason });
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

export async function resolveApprovers(params: {
  role_code: string;
  amount?: string | number;
  category?: string;
  supplier_id?: string;
}): Promise<import("@/lib/types").ResolveApproversResponse> {
  const { data } = await api.get<import("@/lib/types").ResolveApproversResponse>(
    "/approval/approvers/resolve",
    { params }
  );
  return data;
}

// ---- Approval matrix admin ----

export async function listApproverSeeds(params?: {
  role_code?: string;
  org_unit_id?: string;
  include_inactive?: boolean;
  skip?: number;
  limit?: number;
}): Promise<{ items: import("@/lib/types").ApproverSeed[]; total: number }> {
  const { data } = await api.get<{ items: import("@/lib/types").ApproverSeed[]; total: number }>(
    "/approval/approvers",
    { params }
  );
  return data;
}

export async function getApproverSeed(id: string): Promise<import("@/lib/types").ApproverSeed> {
  const { data } = await api.get<import("@/lib/types").ApproverSeed>(`/approval/approvers/${id}`);
  return data;
}

export async function upsertApproverSeed(
  payload: import("@/lib/types").ApproverSeedUpsert
): Promise<import("@/lib/types").ApproverSeed> {
  const { data } = await api.post<import("@/lib/types").ApproverSeed>("/approval/approvers", payload);
  return data;
}

export async function updateApproverSeed(
  id: string,
  payload: Partial<import("@/lib/types").ApproverSeedUpsert>
): Promise<import("@/lib/types").ApproverSeed> {
  const { data } = await api.patch<import("@/lib/types").ApproverSeed>(`/approval/approvers/${id}`, payload);
  return data;
}

export async function deactivateApproverSeed(id: string): Promise<import("@/lib/types").ApproverSeed> {
  const { data } = await api.delete<import("@/lib/types").ApproverSeed>(`/approval/approvers/${id}`);
  return data;
}

export async function listSlaDefinitions(params?: {
  document_type?: string;
  limit?: number;
}): Promise<{ items: import("@/lib/types").SlaDefinitionEntry[]; total: number }> {
  const { data } = await api.get<{ items: import("@/lib/types").SlaDefinitionEntry[]; total: number }>(
    "/approval/sla/definitions",
    { params }
  );
  return data;
}

export async function createSlaDefinition(payload: {
  document_type: string;
  role_code?: string;
  node_type?: string;
  target_duration_minutes: number;
  severity?: string;
}): Promise<import("@/lib/types").SlaDefinitionEntry> {
  const { data } = await api.post<import("@/lib/types").SlaDefinitionEntry>("/approval/sla/definitions", payload);
  return data;
}

export async function getApprovalAnalytics(): Promise<import("@/lib/types").ApprovalAnalytics> {
  const { data } = await api.get<import("@/lib/types").ApprovalAnalytics>("/approval/analytics");
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

// Single-prompt text generation via the configured AI provider (POST
// /ai/generate). Used by the workflow designer's "✨ AI-draft reason" button.
export async function generateAiText(prompt: string, systemPrompt?: string): Promise<string> {
  const { data } = await api.post<{ text: string }>("/ai/generate", {
    prompt,
    system_prompt: systemPrompt,
  });
  return data.text;
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

// Multi-agent P2P pipeline built on Google ADK (adk-service/) -- requisition
// intake -> supplier/sourcing check -> receipt/invoice match. See
// docs/AGENTIC_HACKATHON_SUBMISSION_PLAN.md.
export async function runP2PPipeline(
  request?: string
): Promise<import("@/lib/types").P2PPipelineResponse> {
  const { data } = await api.post<import("@/lib/types").P2PPipelineResponse>(
    "/ai/agents/pipelines/p2p-intake",
    { request: request || "Run the requisition-to-receipt pipeline" }
  );
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

export interface GlAccount {
  code: string;
  description?: string | null;
  account_type?: string | null;
  is_active: boolean;
}

// Full chart of accounts is small master data (admin-uploaded CSV) -- no
// server-side search param exists, so callers fetch once and filter
// client-side (see AccountCodeInput).
export async function listGlAccounts(): Promise<GlAccount[]> {
  const { data } = await api.get<GlAccount[]>("/gl-accounts");
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

export async function getCommodityMatchingPolicyCount(): Promise<number> {
  const { data } = await api.get<unknown[]>("/commodity-codes/policies");
  return data.length;
}

export async function uploadCommodityMatchingPolicy(file: File): Promise<{ loaded: number; errors?: string[] }> {
  return uploadCsv<{ loaded: number; errors?: string[] }>("/commodity-codes/policies/upload", file);
}

export async function downloadCommodityMatchingPolicy(): Promise<void> {
  return downloadCsv("/commodity-codes/policies/export", "commodity_matching_policies.csv");
}

export async function deleteAllCommodityMatchingPolicy(): Promise<{ deleted: number }> {
  const { data } = await api.delete<{ deleted: number }>("/commodity-codes/policies");
  return data;
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

// ---- Universal Template Framework (Phase 1) ----

export async function getEffectiveTemplate(
  module: string
): Promise<import("@/lib/types").TemplateDefinition> {
  const { data } = await api.get<import("@/lib/types").TemplateDefinition>(
    `/templates/${module}/effective`
  );
  return data;
}

export async function getTemplateResponse(
  entityType: string,
  entityId: string
): Promise<import("@/lib/types").TemplateResponse> {
  const { data } = await api.get<import("@/lib/types").TemplateResponse>(
    `/templates/responses/${entityType}/${entityId}`
  );
  return data;
}

// ---- Template Admin (Phase 2 authoring) ----

export async function listTemplatesAdmin(params?: {
  module?: string;
  status?: string;
  skip?: number;
  limit?: number;
}): Promise<import("@/lib/types").TemplateDefinitionListResponse> {
  const { data } = await api.get<import("@/lib/types").TemplateDefinitionListResponse>(
    "/templates/admin",
    { params }
  );
  return data;
}

export async function getTemplateAdmin(
  templateId: string
): Promise<import("@/lib/types").TemplateDefinition> {
  const { data } = await api.get<import("@/lib/types").TemplateDefinition>(
    `/templates/admin/${templateId}`
  );
  return data;
}

export async function createTemplateAdmin(
  payload: import("@/lib/types").TemplateDefinitionInput
): Promise<import("@/lib/types").TemplateDefinition> {
  const { data } = await api.post<import("@/lib/types").TemplateDefinition>(
    "/templates/admin",
    payload
  );
  return data;
}

export async function updateTemplateAdmin(
  templateId: string,
  payload: import("@/lib/types").TemplateDefinitionInput
): Promise<import("@/lib/types").TemplateDefinition> {
  const { data } = await api.put<import("@/lib/types").TemplateDefinition>(
    `/templates/admin/${templateId}`,
    payload
  );
  return data;
}

export async function publishTemplateAdmin(
  templateId: string,
  effectiveDate?: string
): Promise<import("@/lib/types").TemplateDefinition> {
  const { data } = await api.post<import("@/lib/types").TemplateDefinition>(
    `/templates/admin/${templateId}/publish`,
    { effective_date: effectiveDate || undefined }
  );
  return data;
}

export async function deleteTemplateAdmin(templateId: string): Promise<void> {
  await api.delete(`/templates/admin/${templateId}`);
}

// ---- Admin Email Templates (backlog Section 1) ----

export async function listEmailTemplatesAdmin(): Promise<
  import("@/lib/types").EmailTemplateCatalogListResponse
> {
  const { data } = await api.get<import("@/lib/types").EmailTemplateCatalogListResponse>(
    "/admin/email-templates"
  );
  return data;
}

export async function getEmailTemplateAdmin(
  emailType: string
): Promise<import("@/lib/types").EmailTemplateDetailResponse> {
  const { data } = await api.get<import("@/lib/types").EmailTemplateDetailResponse>(
    `/admin/email-templates/${encodeURIComponent(emailType)}`
  );
  return data;
}

export async function upsertEmailTemplateAdmin(
  emailType: string,
  payload: import("@/lib/types").EmailTemplateOverrideUpsert
): Promise<import("@/lib/types").EmailTemplateOverrideOut> {
  const { data } = await api.put<import("@/lib/types").EmailTemplateOverrideOut>(
    `/admin/email-templates/${encodeURIComponent(emailType)}`,
    payload
  );
  return data;
}

// ---- Static catalog (backlog Section 3) ----

export async function listCatalogItems(params?: {
  category?: string;
}): Promise<import("@/lib/types").CatalogItemListResponse> {
  const { data } = await api.get<import("@/lib/types").CatalogItemListResponse>("/catalog", { params });
  return data;
}

// ---- Reports & Analytics (backlog Section 4) ----

export async function getSupplierScorecard(): Promise<
  import("@/lib/types").SupplierScorecardResponse
> {
  const { data } = await api.get<import("@/lib/types").SupplierScorecardResponse>(
    "/analytics/supplier-scorecard"
  );
  return data;
}

export async function getPoAging(): Promise<import("@/lib/types").PoAgingResponse> {
  const { data } = await api.get<import("@/lib/types").PoAgingResponse>("/analytics/po-aging");
  return data;
}

export async function getApprovalBottlenecks(): Promise<
  import("@/lib/types").ApprovalBottleneckResponse
> {
  const { data } = await api.get<import("@/lib/types").ApprovalBottleneckResponse>(
    "/analytics/approval-bottlenecks"
  );
  return data;
}

export async function getExceptionDashboard(): Promise<
  import("@/lib/types").ExceptionDashboardResponse
> {
  const { data } = await api.get<import("@/lib/types").ExceptionDashboardResponse>(
    "/analytics/exceptions"
  );
  return data;
}

export async function retryExceptionRequisition(
  requisitionId: string
): Promise<import("@/lib/types").ExceptionRetryResponse> {
  const { data } = await api.post<import("@/lib/types").ExceptionRetryResponse>(
    `/analytics/exceptions/${requisitionId}/retry`
  );
  return data;
}

// ---- Requisition attachments (backlog Section 5) ----

export async function listRequisitionAttachments(
  requisitionId: string
): Promise<import("@/lib/types").ProcurementAttachment[]> {
  const { data } = await api.get<import("@/lib/types").ProcurementAttachment[]>(
    `/procurement/requisitions/${requisitionId}/attachments`
  );
  return data;
}

export async function addRequisitionAttachment(
  requisitionId: string,
  payload: import("@/lib/types").ProcurementAttachmentCreate
): Promise<import("@/lib/types").ProcurementAttachment> {
  const { data } = await api.post<import("@/lib/types").ProcurementAttachment>(
    `/procurement/requisitions/${requisitionId}/attachments`,
    payload
  );
  return data;
}

// ---- Invoice reconciliation / price-mismatch alerts (backlog Section 5) ----

export async function getInvoiceExceptions(
  invoiceId: string
): Promise<import("@/lib/types").ProcurementInvoiceException[]> {
  const { data } = await api.get<import("@/lib/types").ProcurementInvoiceException[]>(
    `/procurement/invoices/${invoiceId}/exceptions`
  );
  return data;
}

// ---- Supplier Requests ----

export async function listSupplierRequests(params?: {
  skip?: number;
  limit?: number;
  search?: string;
  status?: string;
}): Promise<import("@/lib/types").SupplierRequestListResponse> {
  const { data } = await api.get<import("@/lib/types").SupplierRequestListResponse>(
    "/suppliers/requests",
    { params }
  );
  return data;
}

export async function getSupplierRequest(
  id: string
): Promise<import("@/lib/types").SupplierRequest> {
  const { data } = await api.get<import("@/lib/types").SupplierRequest>(
    `/suppliers/requests/${id}`
  );
  return data;
}

export async function createSupplierRequest(payload: {
  title: string;
  requestor_id: string;
  supplier_type_id?: string;
  answers?: import("@/lib/types").TemplateAnswers;
}): Promise<import("@/lib/types").SupplierRequest> {
  const { data } = await api.post<import("@/lib/types").SupplierRequest>(
    "/suppliers/requests",
    payload
  );
  return data;
}

export async function transitionSupplierRequest(
  id: string,
  action: "submit" | "approve" | "reject" | "cancel"
): Promise<import("@/lib/types").SupplierRequest> {
  const { data } = await api.post<import("@/lib/types").SupplierRequest>(
    `/suppliers/requests/${id}/transition`,
    { action }
  );
  return data;
}

// ---- Supplier Types (FS Section 4) ----

export async function listSupplierTypes(params?: {
  active_only?: boolean;
  skip?: number;
  limit?: number;
}): Promise<import("@/lib/types").SupplierTypeListResponse> {
  const { data } = await api.get<import("@/lib/types").SupplierTypeListResponse>(
    "/supplier-types",
    { params }
  );
  return data;
}

export async function getSupplierType(
  typeId: string
): Promise<import("@/lib/types").SupplierType> {
  const { data } = await api.get<import("@/lib/types").SupplierType>(
    `/supplier-types/${typeId}`
  );
  return data;
}

export async function createSupplierType(
  payload: import("@/lib/types").SupplierTypeInput
): Promise<import("@/lib/types").SupplierType> {
  const { data } = await api.post<import("@/lib/types").SupplierType>(
    "/supplier-types",
    payload
  );
  return data;
}

export async function updateSupplierType(
  typeId: string,
  payload: Partial<import("@/lib/types").SupplierTypeInput>
): Promise<import("@/lib/types").SupplierType> {
  const { data } = await api.put<import("@/lib/types").SupplierType>(
    `/supplier-types/${typeId}`,
    payload
  );
  return data;
}

export async function deactivateSupplierType(
  typeId: string
): Promise<import("@/lib/types").SupplierType> {
  const { data } = await api.post<import("@/lib/types").SupplierType>(
    `/supplier-types/${typeId}/deactivate`
  );
  return data;
}

// ---- Excel Registration ----

export async function listSupplierRegistrations(params?: {
  status?: string;
  skip?: number;
  limit?: number;
}): Promise<import("@/lib/types").SupplierRegistrationListResponse> {
  const { data } = await api.get<import("@/lib/types").SupplierRegistrationListResponse>(
    "/suppliers/registrations",
    { params }
  );
  return data;
}

export async function getSupplierRegistration(
  id: string
): Promise<import("@/lib/types").SupplierRegistrationSummary> {
  const { data } = await api.get<import("@/lib/types").SupplierRegistrationSummary>(
    `/suppliers/registrations/${id}`
  );
  return data;
}

export async function sendSupplierRegistration(
  id: string
): Promise<import("@/lib/types").SupplierRegistrationSummary> {
  const { data } = await api.post<import("@/lib/types").SupplierRegistrationSummary>(
    `/suppliers/registrations/${id}/send`
  );
  return data;
}

export async function downloadRegistrationWorkbook(id: string): Promise<Blob> {
  const { data } = await api.get(`/suppliers/registrations/${id}/workbook`, {
    responseType: "blob",
  });
  return data as Blob;
}

export async function importRegistrationWorkbook(
  id: string,
  file: File
): Promise<import("@/lib/types").RegistrationImportResult> {
  const form = new FormData();
  form.append("file", file);
  const { data } = await api.post<import("@/lib/types").RegistrationImportResult>(
    `/suppliers/registrations/${id}/import`,
    form,
    { headers: { "Content-Type": "multipart/form-data" } }
  );
  return data;
}

export async function downloadRegistrationErrorReport(id: string): Promise<Blob> {
  const { data } = await api.get(`/suppliers/registrations/${id}/error-report`, {
    responseType: "blob",
  });
  return data as Blob;
}

// ---- Preferred Supplier Framework (Phase 3-5) ----

export async function listPreferredStatuses(params?: {
  status?: string;
  category?: string;
  region?: string;
}): Promise<import("@/lib/types").PreferredSupplierListResponse> {
  const { data } = await api.get<import("@/lib/types").PreferredSupplierListResponse>(
    "/suppliers/preferred-statuses",
    { params }
  );
  return data;
}

export async function getPreferredStatus(
  supplierId: string
): Promise<import("@/lib/types").PreferredSupplierStatus> {
  const { data } = await api.get<import("@/lib/types").PreferredSupplierStatus>(
    `/suppliers/${supplierId}/preferred`
  );
  return data;
}

export async function recomputePreferredStatus(
  supplierId: string
): Promise<import("@/lib/types").PreferredSupplierStatus> {
  const { data } = await api.post<import("@/lib/types").PreferredSupplierStatus>(
    `/suppliers/${supplierId}/preferred/recompute`
  );
  return data;
}

export async function recomputeAllPreferredStatuses(): Promise<
  import("@/lib/types").PreferredSupplierListResponse
> {
  const { data } = await api.post<import("@/lib/types").PreferredSupplierListResponse>(
    "/suppliers/preferred/recompute-all"
  );
  return data;
}

export async function overridePreferredStatus(
  supplierId: string,
  payload: { status: string; reason: string }
): Promise<import("@/lib/types").PreferredOverrideResponse> {
  const { data } = await api.patch<import("@/lib/types").PreferredOverrideResponse>(
    `/suppliers/${supplierId}/preferred/override`,
    payload
  );
  return data;
}

export async function getSupplierQualification(
  supplierId: string
): Promise<import("@/lib/types").SupplierQualification> {
  const { data } = await api.get<import("@/lib/types").SupplierQualification>(
    `/suppliers/${supplierId}/qualification`
  );
  return data;
}

export async function upsertSupplierQualification(
  supplierId: string,
  payload: { score: number; status?: string; valid_until?: string | null; notes?: string | null }
): Promise<import("@/lib/types").SupplierQualification> {
  const { data } = await api.put<import("@/lib/types").SupplierQualification>(
    `/suppliers/${supplierId}/qualification`,
    payload
  );
  return data;
}

export async function inviteSupplierToSourcingEvent(
  eventId: string,
  supplierId: string
): Promise<{ id: string; event_id: string; supplier_id: string; status: string }> {
  const { data } = await api.post(`/sourcing/events/${eventId}/invitations`, {
    supplier_id: supplierId,
  });
  return data;
}
