// Supplier knowledge graph client (HackFW Supplier Relationship Management track).
// Mirrors backend/app/services/supplier_graph.py and routers/supplier_graph.py.
import { api } from "@/lib/api";

export type CertStatus = "valid" | "expiring" | "expired";

export interface CertificationSummary {
  id: string;
  cert_type: string;
  certificate_number: string | null;
  issuing_body: string | null;
  scope: string | null;
  issued_on: string | null;
  expires_on: string | null;
  status: CertStatus;
  tenant_owned: boolean;
}

export interface SupplierSummary {
  id: string;
  name: string;
  lifecycle_status: string;
  is_active: boolean;
  risk_level: string | null;
  risk_score: number | null;
  payment_terms: string | null;
  preferred_payment_method: string | null;
  preferred_status: string | null;
  qualification_grade: string | null;
  qualification_status: string | null;
  certifications?: CertificationSummary[];
  valid_certifications: number;
  expiring_certifications: number;
  expired_certifications: number;
  open_po_count: number;
  open_po_value: number;
  open_invoice_count: number;
  open_invoice_value: number;
  open_exceptions: number;
  overdue_invoices: number;
  next_payment_due: string | null;
  commodity_count: number;
  parent_supplier_id: string | null;
}

export interface PurchaseOrderSummary {
  id: string;
  order_number: string;
  status: string;
  acknowledgment_status: string;
  amount: number;
  currency: string;
  payment_terms: string | null;
  earliest_need_by: string | null;
}

export interface InvoiceSummary {
  id: string;
  invoice_number: string;
  status: string;
  match_status: string;
  block_status: string;
  amount: number;
  currency: string;
  purchase_order_id: string | null;
  open_exceptions: number;
  due_date: string | null;
  days_until_due: number | null;
}

export type GraphNode =
  | { id: string; type: "supplier"; label: string; data: SupplierSummary }
  | { id: string; type: "commodity"; label: string; data: { code: string | null; title: string } }
  | { id: string; type: "certification"; label: string; data: { cert_type: string } }
  | { id: string; type: "purchase_order"; label: string; data: PurchaseOrderSummary }
  | { id: string; type: "invoice"; label: string; data: InvoiceSummary };

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  type: "SUPPLIES" | "HOLDS" | "HAS_OPEN_PO" | "BILLED_BY" | "PARENT_OF";
  // SUPPLIES: spend/lines/last_unit_price/last_ordered/parts; HOLDS: CertificationSummary
  data: Record<string, unknown>;
}

export interface SupplierGraphStats {
  suppliers: number;
  commodities: number;
  certification_types: number;
  open_purchase_orders: number;
  open_po_value: number;
  open_invoices: number;
  open_invoice_value: number;
  open_exceptions: number;
  expiring_certifications: number;
  expired_certifications: number;
  single_source_commodities: number;
}

export interface SupplierGraphResponse {
  nodes: GraphNode[];
  edges: GraphEdge[];
  stats: SupplierGraphStats;
  filters: { supplier_id: string | null; commodity: string | null; cert_type: string | null; include_documents: boolean };
  as_of: string;
}

export interface CertifiedSource {
  supplier: SupplierSummary;
  certification: CertificationSummary | null;
  certification_standing: CertStatus | "missing" | "not_required";
  eligible: boolean;
  matched_commodities: { key: string; code: string | null; title: string }[];
  history: { spend: number; lines: number; last_unit_price: number | null; last_ordered: string | null };
  open_purchase_orders: PurchaseOrderSummary[];
  open_invoices: InvoiceSummary[];
}

export interface CertifiedSourcesResponse {
  commodity: string;
  cert_type: string | null;
  matched_commodities: { key: string; code: string | null; title: string }[];
  eligible_count: number;
  sources: CertifiedSource[];
  as_of: string;
}

export interface SupplierCertification extends CertificationSummary {
  supplier_id: string;
  supplier_name: string | null;
}

export async function getSupplierGraph(params?: {
  supplier_id?: string;
  commodity?: string;
  cert_type?: string;
  include_documents?: boolean;
}): Promise<SupplierGraphResponse> {
  const { data } = await api.get<SupplierGraphResponse>("/supplier-graph", { params });
  return data;
}

export async function findCertifiedSources(params: {
  commodity: string;
  cert_type?: string;
}): Promise<CertifiedSourcesResponse> {
  const { data } = await api.get<CertifiedSourcesResponse>("/supplier-graph/sources", { params });
  return data;
}

export async function listSupplierCertifications(supplierId?: string): Promise<SupplierCertification[]> {
  const { data } = await api.get<SupplierCertification[]>("/supplier-certifications", {
    params: supplierId ? { supplier_id: supplierId } : undefined,
  });
  return data;
}

export async function createSupplierCertification(payload: {
  supplier_id: string;
  cert_type: string;
  certificate_number?: string;
  issuing_body?: string;
  scope?: string;
  issued_on?: string;
  expires_on?: string;
}): Promise<SupplierCertification> {
  const { data } = await api.post<SupplierCertification>("/supplier-certifications", payload);
  return data;
}

export async function deleteSupplierCertification(id: string): Promise<void> {
  await api.delete(`/supplier-certifications/${id}`);
}

export const money = (n: number | null | undefined, currency = "USD") =>
  new Intl.NumberFormat("en-US", { style: "currency", currency, maximumFractionDigits: 0 }).format(n ?? 0);

export const unitPrice = (n: number | null | undefined, currency = "USD") =>
  new Intl.NumberFormat("en-US", { style: "currency", currency, minimumFractionDigits: 2, maximumFractionDigits: 4 }).format(n ?? 0);
