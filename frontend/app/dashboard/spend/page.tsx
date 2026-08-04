"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getSpendAnalytics, getSavingsSummary, extractErrorMessage } from "@/lib/api";
import type { SavingsSummaryResponse, SpendAnalyticsResponse } from "@/lib/types";

export default function SpendPage() {
  const [spend, setSpend] = useState<SpendAnalyticsResponse | null>(null);
  const [savings, setSavings] = useState<SavingsSummaryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const [spendData, savingsData] = await Promise.all([getSpendAnalytics(), getSavingsSummary()]);
        setSpend(spendData);
        setSavings(savingsData);
      } catch (err) {
        setError(extractErrorMessage(err));
      } finally {
        setLoading(false);
      }
    }

    load();
  }, []);

  if (loading) {
    return <p className="text-sm text-slate-400">Loading analytics...</p>;
  }

  if (error) {
    return <p className="text-sm text-red-600">{error}</p>;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Spend & Savings</h1>
        <Link
          href="/dashboard/spend/reports"
          className="rounded-md bg-brand-600 px-3 py-2 text-sm font-medium text-white hover:bg-brand-700"
        >
          Reports & Analytics
        </Link>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="card">
          <p className="text-sm text-slate-500">Total spend</p>
          <p className="mt-2 text-3xl font-semibold">
            {spend?.currency} {spend?.total_spend}
          </p>
        </div>
        <div className="card">
          <p className="text-sm text-slate-500">Savings tracked</p>
          <p className="mt-2 text-3xl font-semibold">{savings?.total_savings}</p>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="card">
          <h2 className="font-semibold">Spend by category</h2>
          <ul className="mt-3 space-y-2 text-sm">
            {spend?.spend_by_category?.map((item) => (
              <li key={item.category} className="flex justify-between rounded bg-slate-50 px-3 py-2">
                <span>{item.category}</span>
                <span>{item.amount}</span>
              </li>
            ))}
          </ul>
        </div>
        <div className="card">
          <h2 className="font-semibold">Top suppliers</h2>
          <ul className="mt-3 space-y-2 text-sm">
            {spend?.top_suppliers?.map((item) => (
              <li key={item.supplier_name} className="flex justify-between rounded bg-slate-50 px-3 py-2">
                <span>{item.supplier_name}</span>
                <span>{item.total_spend}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
