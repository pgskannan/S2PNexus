"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { getContract, extractErrorMessage } from "@/lib/api";
import type { Contract } from "@/lib/types";

export default function ContractDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [contract, setContract] = useState<Contract | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      const data = await getContract(params.id);
      setContract(data);
    } catch (err) {
      setError(extractErrorMessage(err));
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params.id]);

  if (error && !contract) {
    return <p className="text-sm text-red-600">{error}</p>;
  }

  if (!contract) {
    return <p className="text-sm text-slate-400">Loading...</p>;
  }

  return (
    <div className="max-w-2xl space-y-6">
      <button
        onClick={() => router.push("/dashboard/contracts")}
        className="text-sm text-brand-600 hover:underline"
      >
        &larr; Back to contracts
      </button>

      <div className="card space-y-4">
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-xl font-semibold">{contract.title}</h1>
            <p className="mt-1 text-sm text-slate-500">
              {contract.description || "No description"}
            </p>
          </div>
          <span className="badge bg-slate-100 text-slate-700 capitalize">
            {contract.status}
          </span>
        </div>

        <dl className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <dt className="text-slate-500">Contract number</dt>
            <dd>{contract.contract_number}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Contract type</dt>
            <dd>{contract.contract_type}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Value</dt>
            <dd>{contract.value ? `${contract.currency} ${contract.value}` : "—"}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Start date</dt>
            <dd>{new Date(contract.start_date).toLocaleDateString()}</dd>
          </div>
          <div>
            <dt className="text-slate-500">End date</dt>
            <dd>{contract.end_date ? new Date(contract.end_date).toLocaleDateString() : "—"}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Approval status</dt>
            <dd className="capitalize">{contract.approval_status}</dd>
          </div>
        </dl>
      </div>
    </div>
  );
}
