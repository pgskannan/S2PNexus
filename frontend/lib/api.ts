import axios, { AxiosError } from "axios";
import { useAuthStore } from "@/lib/auth-store";
import type {
  AgentQueryResponse,
  Requisition,
  RequisitionListResponse,
  Supplier,
  SupplierListResponse,
  Token,
  User,
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
