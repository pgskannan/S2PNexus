"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { listRequisitions, listSuppliers } from "@/lib/api";
import { useAuthStore } from "@/lib/auth-store";

export default function DashboardPage() {
  const user = useAuthStore((s) => s.user);
  const [reqTotal, setReqTotal] = useState<number | null>(null);
  const [supplierTotal, setSupplierTotal] = useState<number | null>(null);

  useEffect(() => {
    listRequisitions().then((r) => setReqTotal(r.total)).catch(() => setReqTotal(0));
    listSuppliers().then((r) => setSupplierTotal(r.total)).catch(() => setSupplierTotal(0));
  }, []);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold">
          Welcome back{user ? `, ${user.full_name.split(" ")[0]}` : ""}
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          Here&apos;s what&apos;s happening across your S2P operations.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div className="card">
          <p className="text-sm text-slate-500">Requisitions</p>
          <p className="mt-2 text-3xl font-semibold">
            {reqTotal === null ? "..." : reqTotal}
          </p>
          <Link
            href="/dashboard/requisitions"
            className="mt-3 inline-block text-sm text-brand-600 hover:underline"
          >
            View all
          </Link>
        </div>
        <div className="card">
          <p className="text-sm text-slate-500">Suppliers</p>
          <p className="mt-2 text-3xl font-semibold">
            {supplierTotal === null ? "..." : supplierTotal}
          </p>
          <Link
            href="/dashboard/suppliers"
            className="mt-3 inline-block text-sm text-brand-600 hover:underline"
          >
            View all
          </Link>
        </div>
        <div className="card">
          <p className="text-sm text-slate-500">AI Agent</p>
          <p className="mt-2 text-sm text-slate-600">
            Ask the orchestrator to look up or act on procurement, supplier,
            contract, sourcing, or spend data.
          </p>
          <Link
            href="/dashboard/agent"
            className="mt-3 inline-block text-sm text-brand-600 hover:underline"
          >
            Try it
          </Link>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Link href="/dashboard/requisitions/new" className="card hover:border-brand-300">
          <p className="font-medium text-brand-700">+ New Requisition</p>
          <p className="mt-1 text-sm text-slate-500">
            Start a purchase requisition for a business need.
          </p>
        </Link>
        <Link href="/dashboard/suppliers/new" className="card hover:border-brand-300">
          <p className="font-medium text-brand-700">+ New Supplier</p>
          <p className="mt-1 text-sm text-slate-500">
            Add a supplier to your vendor master.
          </p>
        </Link>
      </div>
    </div>
  );
}
