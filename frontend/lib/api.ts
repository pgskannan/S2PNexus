import axios, { AxiosError } from "axios";
import { useAuthStore } from "@/lib/auth-store";
import type {
  AgentQueryResponse,
  Contract,
  ContractListResponse,
  Requisition,
  RequisitionListResponse,
  SavingsListResponse,
  SavingsSummaryResponse,
  SourcingEvent,
  SourcingEventListResponse,
  SpendAnalyticsResponse,
  Supplier,
  SupplierListResponse,
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
