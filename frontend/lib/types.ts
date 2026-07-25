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

export interface Requisition {
  id: string;
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
  created_at: string;
  updated_at: string;
}

export interface SupplierListResponse {
  items: Supplier[];
  total: number;
  skip: number;
  limit: number;
}

export interface AgentQueryResponse {
  agent_name: string;
  success: boolean;
  message: string;
  data: Record<string, unknown>;
  plan: string[];
  explanation: string;
}
