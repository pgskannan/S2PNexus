"use client";

// Supplier knowledge graph (HackFW: MADE Challenge, Supplier Relationship Management track).
//
// Three columns: certifications | suppliers | commodities, laid out so lines
// cross as little as possible. Supplier cards carry live order state (open
// POs, open invoices, exceptions, next payment due). The search bar answers
// the track's core question -- "which certified supplier can ship this part,
// what's open with them, and when do they get paid?" -- via
// GET /supplier-graph/sources, and highlights the answer in the graph.

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import ReactFlow, {
  Background,
  Controls,
  Handle,
  Position,
  ReactFlowProvider,
  useReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from "reactflow";
import "reactflow/dist/style.css";
import { extractErrorMessage } from "@/lib/api";
import {
  createSupplierCertification,
  findCertifiedSources,
  getSupplierGraph,
  money,
  unitPrice,
  type CertificationSummary,
  type CertifiedSourcesResponse,
  type GraphEdge,
  type GraphNode,
  type InvoiceSummary,
  type PurchaseOrderSummary,
  type SupplierGraphResponse,
  type SupplierSummary,
} from "@/lib/supplierGraph";

// ---------------------------------------------------------------------------
// Visual vocabulary
// ---------------------------------------------------------------------------

const CERT_COLORS: Record<string, string> = {
  valid: "#16a34a",
  expiring: "#d97706",
  expired: "#dc2626",
};

const STANDING_LABEL: Record<string, string> = {
  valid: "Certified",
  expiring: "Cert expiring",
  expired: "Cert expired",
  missing: "No certificate",
  not_required: "No cert required",
};

const STANDING_CLASS: Record<string, string> = {
  valid: "bg-green-50 text-green-700",
  expiring: "bg-amber-50 text-amber-700",
  expired: "bg-red-50 text-red-700",
  missing: "bg-slate-100 text-slate-600",
  not_required: "bg-slate-100 text-slate-600",
};

type Dimmable = { dimmed?: boolean; highlighted?: boolean; selected?: boolean };

function SupplierNodeView({ data }: NodeProps<SupplierSummary & Dimmable>) {
  const warn = data.open_exceptions > 0 || data.overdue_invoices > 0;
  return (
    <div
      className={`w-60 rounded-lg border bg-white px-3 py-2 text-left shadow-sm transition-opacity ${
        data.selected ? "border-brand-600 ring-2 ring-brand-200" : data.highlighted ? "border-green-600 ring-2 ring-green-200" : "border-slate-300"
      } ${data.dimmed ? "opacity-25" : ""}`}
    >
      <Handle id="left" type="source" position={Position.Left} style={{ opacity: 0 }} />
      <Handle id="right" type="source" position={Position.Right} style={{ opacity: 0 }} />
      <div className="flex items-start justify-between gap-2">
        <p className="truncate text-sm font-semibold text-slate-900" title={data.name}>
          {data.name}
        </p>
        {data.preferred_status && data.preferred_status !== "none" && (
          <span className="badge shrink-0 bg-brand-50 px-1.5 text-[10px] uppercase text-brand-700">{data.preferred_status}</span>
        )}
      </div>
      <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-slate-500">
        <span>{data.open_po_count} open PO{data.open_po_count === 1 ? "" : "s"}</span>
        <span>{data.open_invoice_count} open inv.</span>
        {data.risk_level && <span>risk {data.risk_level}</span>}
      </div>
      {warn && (
        <p className="mt-1 text-[11px] font-medium text-red-600">
          {data.open_exceptions > 0 && `${data.open_exceptions} match exception${data.open_exceptions === 1 ? "" : "s"}`}
          {data.open_exceptions > 0 && data.overdue_invoices > 0 && " · "}
          {data.overdue_invoices > 0 && `${data.overdue_invoices} overdue`}
        </p>
      )}
    </div>
  );
}

function CommodityNodeView({ data }: NodeProps<{ code: string | null; title: string; suppliers: number } & Dimmable>) {
  return (
    <div
      className={`w-52 rounded-md border px-3 py-1.5 text-left shadow-sm ${
        data.highlighted ? "border-green-600 bg-green-50" : "border-sky-300 bg-sky-50"
      } ${data.dimmed ? "opacity-25" : ""}`}
    >
      <Handle type="target" position={Position.Left} style={{ opacity: 0 }} />
      <p className="truncate text-xs font-semibold text-sky-900" title={data.title}>
        {data.title}
      </p>
      <p className="text-[10px] text-sky-700">
        {data.code ?? "free text"} · {data.suppliers} source{data.suppliers === 1 ? "" : "s"}
        {data.suppliers === 1 && <span className="ml-1 font-semibold text-amber-700">single-source</span>}
      </p>
    </div>
  );
}

function CertNodeView({ data }: NodeProps<{ cert_type: string; holders: number } & Dimmable>) {
  return (
    <div
      className={`w-44 rounded-md border px-3 py-1.5 text-right shadow-sm ${
        data.highlighted ? "border-green-600 bg-green-50" : "border-violet-300 bg-violet-50"
      } ${data.dimmed ? "opacity-25" : ""}`}
    >
      <Handle type="target" position={Position.Right} style={{ opacity: 0 }} />
      <p className="truncate text-xs font-semibold text-violet-900" title={data.cert_type}>
        {data.cert_type}
      </p>
      <p className="text-[10px] text-violet-700">
        {data.holders} holder{data.holders === 1 ? "" : "s"}
      </p>
    </div>
  );
}

const nodeTypes = { supplier: SupplierNodeView, commodity: CommodityNodeView, certification: CertNodeView };

// ---------------------------------------------------------------------------
// Layout: 3 columns, side columns ordered by the mean row of their suppliers
// (barycenter heuristic) so edges mostly run straight across.
// ---------------------------------------------------------------------------

const COL_X = { certification: 0, supplier: 330, commodity: 700 };
const ROW_H = { supplier: 96, side: 58 };

function layout(
  graph: SupplierGraphResponse,
  highlight: Set<string> | null,
  selectedId: string | null,
): { nodes: Node[]; edges: Edge[] } {
  const suppliers = graph.nodes.filter((n) => n.type === "supplier");
  const certs = graph.nodes.filter((n) => n.type === "certification");
  const comms = graph.nodes.filter((n) => n.type === "commodity");
  const rowOf = new Map(suppliers.map((s, i) => [s.id, i]));

  const neighbours = new Map<string, string[]>();
  for (const e of graph.edges) {
    if (e.type === "SUPPLIES" || e.type === "HOLDS") {
      neighbours.set(e.target, [...(neighbours.get(e.target) ?? []), e.source]);
    }
  }
  const bary = (id: string) => {
    const rows = (neighbours.get(id) ?? []).map((s) => rowOf.get(s) ?? 0);
    return rows.length ? rows.reduce((a, b) => a + b, 0) / rows.length : 0;
  };
  const sortSide = (list: GraphNode[]) => [...list].sort((a, b) => bary(a.id) - bary(b.id));

  // Each side node sits level with the average row of its suppliers, then
  // overlapping ones are pushed down just enough to stay readable.
  const place = (list: GraphNode[]) => {
    const out = new Map<string, number>();
    let next = 0;
    for (const n of list) {
      const y = Math.max(next, bary(n.id) * ROW_H.supplier + 10);
      out.set(n.id, y);
      next = y + ROW_H.side;
    }
    return out;
  };
  const certY = place(sortSide(certs));
  const commY = place(sortSide(comms));

  // Highlighting: when a search is active, everything not on a path to an
  // eligible supplier fades.
  const lit = new Set<string>();
  if (highlight) {
    for (const id of highlight) lit.add(id);
    for (const e of graph.edges) {
      if (highlight.has(e.source) && (e.type === "SUPPLIES" || e.type === "HOLDS")) lit.add(e.target);
    }
  }
  const dim = (id: string) => (highlight ? !lit.has(id) : false);

  const nodes: Node[] = [
    ...suppliers.map((n) => ({
      id: n.id,
      type: "supplier",
      position: { x: COL_X.supplier, y: (rowOf.get(n.id) ?? 0) * ROW_H.supplier },
      data: { ...(n.data as SupplierSummary), dimmed: dim(n.id), highlighted: highlight?.has(n.id), selected: n.id === selectedId },
    })),
    ...certs.map((n) => ({
      id: n.id,
      type: "certification",
      position: { x: COL_X.certification, y: certY.get(n.id) ?? 0 },
      data: { ...n.data, holders: neighbours.get(n.id)?.length ?? 0, dimmed: dim(n.id), highlighted: highlight ? lit.has(n.id) : false },
    })),
    ...comms.map((n) => ({
      id: n.id,
      type: "commodity",
      position: { x: COL_X.commodity, y: commY.get(n.id) ?? 0 },
      data: { ...n.data, suppliers: neighbours.get(n.id)?.length ?? 0, dimmed: dim(n.id), highlighted: highlight ? lit.has(n.id) : false },
    })),
  ];

  const maxSpend = Math.max(1, ...graph.edges.filter((e) => e.type === "SUPPLIES").map((e) => Number(e.data.spend ?? 0)));
  const edges: Edge[] = graph.edges
    .filter((e) => e.type === "SUPPLIES" || e.type === "HOLDS" || e.type === "PARENT_OF")
    .map((e: GraphEdge) => {
      const faded = highlight ? !(highlight.has(e.source) && lit.has(e.target)) : false;
      if (e.type === "HOLDS") {
        const status = String(e.data.status ?? "valid");
        return {
          id: e.id,
          source: e.source,
          sourceHandle: "left",
          target: e.target,
          style: {
            stroke: CERT_COLORS[status] ?? "#94a3b8",
            strokeDasharray: status === "expired" ? "4 4" : undefined,
            strokeWidth: 1.5,
            opacity: faded ? 0.12 : 0.9,
          },
        };
      }
      if (e.type === "PARENT_OF") {
        return {
          id: e.id,
          source: e.source,
          sourceHandle: "right",
          target: e.target,
          type: "smoothstep",
          style: { stroke: "#64748b", strokeDasharray: "2 3", opacity: faded ? 0.12 : 0.7 },
        };
      }
      const spend = Number(e.data.spend ?? 0);
      return {
        id: e.id,
        source: e.source,
        sourceHandle: "right",
        target: e.target,
        style: { stroke: "#0284c7", strokeWidth: 1 + 4 * (spend / maxSpend), opacity: faded ? 0.12 : 0.6 },
      };
    });
  return { nodes, edges };
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function SupplierGraphPage() {
  const [graph, setGraph] = useState<SupplierGraphResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [commodityQuery, setCommodityQuery] = useState("");
  const [certQuery, setCertQuery] = useState("");
  const [sources, setSources] = useState<CertifiedSourcesResponse | null>(null);
  // Certificate-only search (no part given): highlight every current holder.
  const [certOnly, setCertOnly] = useState<string | null>(null);
  const [searching, setSearching] = useState(false);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<SupplierGraphResponse | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setGraph(await getSupplierGraph({ include_documents: false }));
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function runSearch(commodity = commodityQuery, cert = certQuery) {
    if (!commodity.trim()) {
      setSources(null);
      setSelectedId(null);
      setCertOnly(cert.trim() || null);
      return;
    }
    setCertOnly(null);
    setSearching(true);
    setError(null);
    setSelectedId(null);
    try {
      setSources(await findCertifiedSources({ commodity: commodity.trim(), cert_type: cert.trim() || undefined }));
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setSearching(false);
    }
  }

  function clearSearch() {
    setSources(null);
    setCertOnly(null);
    setCommodityQuery("");
    setCertQuery("");
  }

  async function selectSupplier(nodeId: string) {
    setSelectedId(nodeId);
    setDetail(null);
    try {
      setDetail(await getSupplierGraph({ supplier_id: nodeId.replace("supplier:", ""), include_documents: true }));
    } catch (err) {
      setError(extractErrorMessage(err));
    }
  }

  const certHolders = useMemo(() => {
    if (!graph || !certOnly) return null;
    const want = normalizeCert(certOnly);
    return graph.edges
      .filter((e) => e.type === "HOLDS" && normalizeCert(String(e.data.cert_type ?? "")) === want)
      .map((e) => ({
        supplierNodeId: e.source,
        name: graph.nodes.find((n) => n.id === e.source)?.label ?? "",
        cert: e.data as unknown as CertificationSummary,
      }))
      .sort((a, b) => STATUS_ORDER[a.cert.status] - STATUS_ORDER[b.cert.status] || a.name.localeCompare(b.name));
  }, [graph, certOnly]);

  const highlight = useMemo(() => {
    if (sources) return new Set(sources.sources.filter((s) => s.eligible).map((s) => `supplier:${s.supplier.id}`));
    if (certHolders) return new Set(certHolders.filter((h) => h.cert.status !== "expired").map((h) => h.supplierNodeId));
    return null;
  }, [sources, certHolders]);
  const flow = useMemo(() => (graph ? layout(graph, highlight, selectedId) : { nodes: [], edges: [] }), [graph, highlight, selectedId]);

  const certTypes = useMemo(
    () => (graph ? graph.nodes.filter((n) => n.type === "certification").map((n) => n.label).sort() : []),
    [graph],
  );
  const commodityOptions = useMemo(
    () =>
      graph
        ? graph.nodes
            .filter((n) => n.type === "commodity")
            .map((n) => ({ value: (n.data as { code: string | null }).code ?? n.label, label: n.label }))
        : [],
    [graph],
  );

  const onNodeClick = useCallback(
    (_: unknown, node: Node) => {
      if (node.type === "supplier") {
        selectSupplier(node.id);
      } else if (node.type === "commodity") {
        const code = (node.data as { code: string | null; title: string }).code ?? (node.data as { title: string }).title;
        setCommodityQuery(code);
        runSearch(code, certQuery);
      } else if (node.type === "certification") {
        const cert = (node.data as { cert_type: string }).cert_type;
        setCertQuery(cert);
        runSearch(commodityQuery, cert);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [certQuery, commodityQuery],
  );

  const stats = graph?.stats;

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-semibold">Supplier Graph</h1>
        <p className="mt-1 text-sm text-slate-500">
          Suppliers, the parts they ship, the certificates they hold, and what is open with them right now, in one view.
          Click a supplier for its live orders, a commodity to find its certified sources.
        </p>
      </div>

      {stats && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <Stat label="Suppliers" value={stats.suppliers} />
          <Stat label="Commodities" value={stats.commodities} sub={`${stats.single_source_commodities} single-source`} warn={stats.single_source_commodities > 0} />
          <Stat label="Open POs" value={stats.open_purchase_orders} sub={money(stats.open_po_value)} />
          <Stat label="Open invoices" value={stats.open_invoices} sub={money(stats.open_invoice_value)} />
          <Stat label="Match exceptions" value={stats.open_exceptions} warn={stats.open_exceptions > 0} />
          <Stat
            label="Certificates at risk"
            value={stats.expiring_certifications + stats.expired_certifications}
            sub={`${stats.expiring_certifications} expiring · ${stats.expired_certifications} expired`}
            warn={stats.expired_certifications > 0}
          />
        </div>
      )}

      <form
        className="card flex flex-wrap items-end gap-3 p-4"
        onSubmit={(e) => {
          e.preventDefault();
          runSearch();
        }}
      >
        <div className="min-w-[14rem] flex-1">
          <label className="label" htmlFor="sg-commodity">
            Part / commodity
          </label>
          <input
            id="sg-commodity"
            className="input-field"
            list="sg-commodities"
            placeholder="UNSPSC code or name, e.g. 3116 or screws"
            value={commodityQuery}
            onChange={(e) => setCommodityQuery(e.target.value)}
          />
          <datalist id="sg-commodities">
            {commodityOptions.map((c) => (
              <option key={c.value} value={c.value}>
                {c.label}
              </option>
            ))}
          </datalist>
        </div>
        <div className="min-w-[12rem]">
          <label className="label" htmlFor="sg-cert">
            Required certificate
          </label>
          <input
            id="sg-cert"
            className="input-field"
            list="sg-certs"
            placeholder="optional, e.g. AS9100D"
            value={certQuery}
            onChange={(e) => setCertQuery(e.target.value)}
          />
          <datalist id="sg-certs">
            {certTypes.map((c) => (
              <option key={c} value={c} />
            ))}
          </datalist>
        </div>
        <button type="submit" className="btn-primary" disabled={searching || (!commodityQuery.trim() && !certQuery.trim())}>
          {searching ? "Searching…" : commodityQuery.trim() || !certQuery.trim() ? "Find certified sources" : "Show certificate holders"}
        </button>
        {(sources || certOnly) && (
          <button type="button" className="btn-secondary" onClick={clearSearch}>
            Clear
          </button>
        )}
      </form>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="flex flex-col gap-4 xl:flex-row">
        <div className="card flex-1 overflow-hidden p-0">
          <Legend />
          <div className="relative h-[720px] border-t border-slate-100">
            {loading ? (
              <p className="p-6 text-sm text-slate-400">Loading supplier graph…</p>
            ) : graph && graph.nodes.length === 0 ? (
              <p className="p-6 text-sm text-slate-400">No suppliers yet.</p>
            ) : (
              <ReactFlowProvider>
                <GraphCanvas nodes={flow.nodes} edges={flow.edges} onNodeClick={onNodeClick} focus={highlight} />
              </ReactFlowProvider>
            )}
          </div>
        </div>

        <aside className="w-full shrink-0 space-y-4 xl:w-[26rem]">
          {selectedId ? (
            <SupplierPanel graph={detail} supplierNodeId={selectedId} onClose={() => setSelectedId(null)} onChanged={load} />
          ) : null}
          {sources ? (
            <SourcesPanel sources={sources} onSelect={(id) => selectSupplier(`supplier:${id}`)} />
          ) : null}
          {certOnly && certHolders ? (
            <CertHoldersPanel certType={certOnly} holders={certHolders} onSelect={selectSupplier} />
          ) : null}
          {!selectedId && !sources && !certOnly ? (
            <div className="card text-sm text-slate-500">
              <p className="font-medium text-slate-700">Try it</p>
              <p className="mt-1">
                Type a part (UNSPSC prefix or name) and, optionally, the certificate it requires. S2PNexus ranks the
                suppliers that have shipped it before by certificate standing, preferred status, open exceptions and risk,
                and shows what you owe each one and when.
              </p>
            </div>
          ) : null}
        </aside>
      </div>
    </div>
  );
}

const STATUS_ORDER: Record<string, number> = { valid: 0, expiring: 1, expired: 2 };

function normalizeCert(v: string) {
  return v.toLowerCase().replace(/[\s\-_:.]+/g, "");
}

// Readable by default: rather than squeezing every supplier into view (cards
// become unreadable past ~10 suppliers), open at a legible zoom aligned to the
// top and let the user scroll; when a search highlights suppliers, zoom to them.
function GraphCanvas({
  nodes,
  edges,
  onNodeClick,
  focus,
}: {
  nodes: Node[];
  edges: Edge[];
  onNodeClick: (e: unknown, n: Node) => void;
  focus: Set<string> | null;
}) {
  const rf = useReactFlow();
  const [ready, setReady] = useState(false);

  const showTop = useCallback(() => {
    const el = document.querySelector(".sg-canvas") as HTMLElement | null;
    const width = el?.clientWidth ?? 900;
    const height = el?.clientHeight ?? 720;
    const contentW = COL_X.commodity + 220;
    const contentH = Math.max(...nodes.map((n) => n.position.y + 90), 1);
    const zoom = Math.max(0.62, Math.min(1, (width - 40) / contentW, (height - 40) / contentH));
    rf.setViewport({ x: Math.max(20, (width - contentW * zoom) / 2), y: 20, zoom }, { duration: 300 });
  }, [nodes, rf]);

  useEffect(() => {
    if (!ready) return;
    // Wait a frame so React Flow has measured the re-laid-out nodes.
    const t = window.setTimeout(() => {
      if (focus && focus.size > 0) {
        rf.fitView({ nodes: nodes.filter((n) => focus.has(n.id)).map((n) => ({ id: n.id })), padding: 0.5, maxZoom: 1, duration: 400 });
      } else {
        showTop();
      }
    }, 80);
    return () => window.clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, focus]);

  return (
    <ReactFlow
      className="sg-canvas"
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      onNodeClick={onNodeClick}
      onInit={() => setReady(true)}
      nodesDraggable
      nodesConnectable={false}
      panOnScroll
      zoomOnScroll={false}
      zoomActivationKeyCode="Control"
      minZoom={0.2}
      maxZoom={1.5}
      proOptions={{ hideAttribution: true }}
    >
      <Background gap={24} color="#e2e8f0" />
      <Controls position="bottom-right" showInteractive={false} />
    </ReactFlow>
  );
}

function CertHoldersPanel({
  certType,
  holders,
  onSelect,
}: {
  certType: string;
  holders: { supplierNodeId: string; name: string; cert: CertificationSummary }[];
  onSelect: (supplierNodeId: string) => void;
}) {
  const current = holders.filter((h) => h.cert.status !== "expired").length;
  return (
    <div className="card space-y-2 p-4">
      <p className="text-sm font-semibold text-slate-900">
        {current} supplier{current === 1 ? "" : "s"} currently hold {certType}
      </p>
      <p className="text-xs text-slate-500">Add a part to rank them by purchase history, price and what is open now.</p>
      {holders.length === 0 && <p className="text-sm text-slate-400">Nobody holds this certificate.</p>}
      <ul className="divide-y divide-slate-100">
        {holders.map((h) => (
          <li key={h.cert.id}>
            <button type="button" onClick={() => onSelect(h.supplierNodeId)} className="flex w-full items-center justify-between gap-2 py-2 text-left text-sm hover:bg-slate-50">
              <span>{h.name}</span>
              <span className={`badge ${STANDING_CLASS[h.cert.status]}`}>
                {h.cert.status}
                {h.cert.expires_on ? ` ${h.cert.expires_on}` : ""}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Stat({ label, value, sub, warn }: { label: string; value: number; sub?: string; warn?: boolean }) {
  return (
    <div className="card p-4">
      <p className="text-xs uppercase text-slate-400">{label}</p>
      <p className={`mt-1 text-2xl font-semibold ${warn ? "text-amber-600" : ""}`}>{value}</p>
      {sub && <p className="text-xs text-slate-500">{sub}</p>}
    </div>
  );
}

function Legend() {
  return (
    <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-1 px-4 py-2 text-[11px] text-slate-600">
      <div className="flex items-center gap-3">
        <span className="font-semibold text-violet-700">Certificates</span>
        <span className="text-slate-300">→</span>
        <span className="font-semibold text-slate-700">Suppliers</span>
        <span className="text-slate-300">→</span>
        <span className="font-semibold text-sky-700">Commodities</span>
        <span className="text-slate-400">· scroll to pan, Ctrl+scroll to zoom</span>
      </div>
      <div className="flex items-center gap-3">
        <LegendLine color={CERT_COLORS.valid} label="valid" />
        <LegendLine color={CERT_COLORS.expiring} label="expiring ≤60d" />
        <LegendLine color={CERT_COLORS.expired} label="expired" dashed />
        <LegendLine color="#0284c7" label="spend" thick />
      </div>
    </div>
  );
}

function LegendLine({ color, label, dashed, thick }: { color: string; label: string; dashed?: boolean; thick?: boolean }) {
  return (
    <span className="flex items-center gap-1">
      <svg width="18" height="6" aria-hidden>
        <line x1="0" y1="3" x2="18" y2="3" stroke={color} strokeWidth={thick ? 4 : 2} strokeDasharray={dashed ? "3 3" : undefined} />
      </svg>
      {label}
    </span>
  );
}

function SourcesPanel({ sources, onSelect }: { sources: CertifiedSourcesResponse; onSelect: (supplierId: string) => void }) {
  const titles = sources.matched_commodities.map((c) => c.title).join(", ");
  return (
    <div className="card space-y-3 p-4">
      <div>
        <p className="text-sm font-semibold text-slate-900">
          {sources.eligible_count} eligible source{sources.eligible_count === 1 ? "" : "s"}
          {sources.cert_type ? ` with ${sources.cert_type}` : ""}
        </p>
        <p className="text-xs text-slate-500">{titles ? `for ${titles}` : `No purchase history matches “${sources.commodity}”.`}</p>
      </div>
      {sources.sources.map((s, i) => {
        const nextDue = s.open_invoices.find((inv) => inv.due_date);
        return (
          <button
            key={s.supplier.id}
            type="button"
            onClick={() => onSelect(s.supplier.id)}
            className={`w-full rounded-md border p-3 text-left hover:bg-slate-50 ${s.eligible ? "border-slate-200" : "border-slate-100 opacity-70"}`}
          >
            <div className="flex items-start justify-between gap-2">
              <p className="text-sm font-semibold">
                {i + 1}. {s.supplier.name}
              </p>
              <span className={`badge ${STANDING_CLASS[s.certification_standing]}`}>{STANDING_LABEL[s.certification_standing]}</span>
            </div>
            <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
              <dt className="text-slate-500">Last price</dt>
              <dd>{s.history.last_unit_price != null ? unitPrice(s.history.last_unit_price) : "—"}{s.history.last_ordered ? ` (${s.history.last_ordered})` : ""}</dd>
              <dt className="text-slate-500">Spend to date</dt>
              <dd>{money(s.history.spend)}</dd>
              <dt className="text-slate-500">Open now</dt>
              <dd>
                {s.open_purchase_orders.length} PO · {s.open_invoices.length} inv.
                {s.supplier.open_exceptions > 0 && <span className="text-red-600"> · {s.supplier.open_exceptions} exc.</span>}
              </dd>
              <dt className="text-slate-500">Next payment</dt>
              <dd>{nextDue ? <DueText inv={nextDue} /> : s.supplier.payment_terms ?? "—"}</dd>
              {s.certification && (
                <>
                  <dt className="text-slate-500">Certificate</dt>
                  <dd>
                    {s.certification.cert_type}
                    {s.certification.expires_on ? ` until ${s.certification.expires_on}` : ""}
                  </dd>
                </>
              )}
            </dl>
          </button>
        );
      })}
    </div>
  );
}

function DueText({ inv }: { inv: InvoiceSummary }) {
  if (!inv.due_date) return <>—</>;
  const d = inv.days_until_due ?? 0;
  return (
    <span className={d < 0 ? "font-medium text-red-600" : d <= 7 ? "text-amber-700" : ""}>
      {money(inv.amount, inv.currency)} on {inv.due_date} ({d < 0 ? `${-d}d overdue` : `in ${d}d`})
    </span>
  );
}

function SupplierPanel({
  graph,
  supplierNodeId,
  onClose,
  onChanged,
}: {
  graph: SupplierGraphResponse | null;
  supplierNodeId: string;
  onClose: () => void;
  onChanged: () => void;
}) {
  const node = graph?.nodes.find((n) => n.id === supplierNodeId);
  const supplier = node?.type === "supplier" ? node.data : null;
  const pos = (graph?.nodes.filter((n) => n.type === "purchase_order") ?? []) as Array<{ id: string; data: PurchaseOrderSummary }>;
  const poIds = new Set(
    graph?.edges.filter((e) => e.type === "HAS_OPEN_PO" && e.source === supplierNodeId).map((e) => e.target) ?? [],
  );
  const invIds = new Set(
    graph?.edges.filter((e) => e.type === "BILLED_BY" && (poIds.has(e.source) || e.source === supplierNodeId)).map((e) => e.target) ?? [],
  );
  const invoices = (graph?.nodes.filter((n) => n.type === "invoice" && invIds.has(n.id)) ?? []) as Array<{ id: string; data: InvoiceSummary }>;
  const alternates = graph?.nodes.filter((n) => n.type === "supplier" && n.id !== supplierNodeId) ?? [];

  return (
    <div className="card space-y-4 p-4">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-base font-semibold">{supplier?.name ?? "Loading…"}</p>
          {supplier && (
            <p className="text-xs text-slate-500">
              {supplier.lifecycle_status}
              {supplier.payment_terms ? ` · ${supplier.payment_terms}` : ""}
              {supplier.qualification_grade ? ` · qualification ${supplier.qualification_grade}` : ""}
            </p>
          )}
        </div>
        <div className="flex items-center gap-2">
          {supplier && (
            <Link className="text-xs text-brand-700 hover:underline" href={`/dashboard/suppliers/${supplier.id}`}>
              Open record
            </Link>
          )}
          <button type="button" className="text-xs text-slate-500 hover:text-slate-800" onClick={onClose}>
            Close
          </button>
        </div>
      </div>

      {supplier && (
        <>
          <section>
            <h3 className="text-xs font-semibold uppercase text-slate-400">Certificates</h3>
            <ul className="mt-1 space-y-1 text-sm">
              {(supplier.certifications ?? []).length === 0 && <li className="text-slate-400">None on file</li>}
              {(supplier.certifications ?? []).map((c: CertificationSummary) => (
                <li key={c.id} className="flex items-center justify-between gap-2">
                  <span>
                    {c.cert_type}
                    {c.issuing_body ? <span className="text-xs text-slate-400"> · {c.issuing_body}</span> : null}
                  </span>
                  <span className={`badge ${STANDING_CLASS[c.status]}`}>
                    {c.status}
                    {c.expires_on ? ` ${c.expires_on}` : ""}
                  </span>
                </li>
              ))}
            </ul>
            <AddCertForm supplierId={supplier.id} onAdded={onChanged} />
          </section>

          <section>
            <h3 className="text-xs font-semibold uppercase text-slate-400">
              Open purchase orders · {money(supplier.open_po_value)}
            </h3>
            <ul className="mt-1 space-y-1 text-sm">
              {pos.filter((p) => poIds.has(p.id)).length === 0 && <li className="text-slate-400">None</li>}
              {pos
                .filter((p) => poIds.has(p.id))
                .map((p) => (
                  <li key={p.id} className="flex justify-between gap-2">
                    <Link className="text-brand-700 hover:underline" href={`/dashboard/purchase-orders/${p.data.id}`}>
                      {p.data.order_number}
                    </Link>
                    <span className="text-xs text-slate-500">
                      {p.data.status} · {money(p.data.amount, p.data.currency)}
                      {p.data.earliest_need_by ? ` · need by ${p.data.earliest_need_by}` : ""}
                    </span>
                  </li>
                ))}
            </ul>
          </section>

          <section>
            <h3 className="text-xs font-semibold uppercase text-slate-400">
              Open invoices · {money(supplier.open_invoice_value)}
            </h3>
            <ul className="mt-1 space-y-1 text-sm">
              {invoices.length === 0 && <li className="text-slate-400">None</li>}
              {invoices.map((inv) => (
                <li key={inv.id}>
                  <div className="flex justify-between gap-2">
                    <Link className="text-brand-700 hover:underline" href={inv.data.purchase_order_id ? `/dashboard/invoices?po=${inv.data.purchase_order_id}` : "/dashboard/invoices"}>
                      {inv.data.invoice_number}
                    </Link>
                    <span className="text-xs text-slate-500">
                      {inv.data.status} / {inv.data.match_status}
                    </span>
                  </div>
                  <p className="text-xs">
                    <DueText inv={inv.data} />
                    {inv.data.open_exceptions > 0 && <span className="text-red-600"> · {inv.data.open_exceptions} exception(s)</span>}
                  </p>
                </li>
              ))}
            </ul>
          </section>

          {alternates.length > 0 && (
            <section>
              <h3 className="text-xs font-semibold uppercase text-slate-400">Alternate sources for the same commodities</h3>
              <p className="mt-1 text-sm text-slate-600">{alternates.map((a) => a.label).join(", ")}</p>
            </section>
          )}
        </>
      )}
    </div>
  );
}

function AddCertForm({ supplierId, onAdded }: { supplierId: string; onAdded: () => void }) {
  const [open, setOpen] = useState(false);
  const [certType, setCertType] = useState("");
  const [expires, setExpires] = useState("");
  const [body, setBody] = useState("");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  if (!open) {
    return (
      <button type="button" className="mt-2 text-xs text-brand-700 hover:underline" onClick={() => setOpen(true)}>
        + Add certificate
      </button>
    );
  }
  return (
    <form
      className="mt-2 space-y-2 rounded-md border border-slate-200 p-2"
      onSubmit={async (e) => {
        e.preventDefault();
        setSaving(true);
        setErr(null);
        try {
          await createSupplierCertification({
            supplier_id: supplierId,
            cert_type: certType,
            issuing_body: body || undefined,
            expires_on: expires || undefined,
          });
          setOpen(false);
          setCertType("");
          setExpires("");
          setBody("");
          onAdded();
        } catch (error) {
          setErr(extractErrorMessage(error));
        } finally {
          setSaving(false);
        }
      }}
    >
      <input className="input-field" placeholder="Certificate, e.g. AS9100D" value={certType} onChange={(e) => setCertType(e.target.value)} required />
      <div className="flex gap-2">
        <input className="input-field" placeholder="Issuing body" value={body} onChange={(e) => setBody(e.target.value)} />
        <input className="input-field" type="date" value={expires} onChange={(e) => setExpires(e.target.value)} aria-label="Expires on" />
      </div>
      {err && <p className="text-xs text-red-600">{err}</p>}
      <div className="flex gap-2">
        <button type="submit" className="btn-primary px-3 py-1" disabled={saving}>
          {saving ? "Saving…" : "Save"}
        </button>
        <button type="button" className="btn-secondary px-3 py-1" onClick={() => setOpen(false)}>
          Cancel
        </button>
      </div>
    </form>
  );
}
