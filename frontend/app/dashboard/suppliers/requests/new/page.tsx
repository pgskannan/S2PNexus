"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import DynamicTemplateForm from "@/components/DynamicTemplateForm";
import {
  createSupplierRequest,
  extractErrorMessage,
  getEffectiveTemplate,
  listSupplierTypes,
  transitionSupplierRequest,
} from "@/lib/api";
import { useAuthStore } from "@/lib/auth-store";
import type { SupplierType, TemplateAnswers, TemplateDefinition } from "@/lib/types";

export default function NewSupplierRequestPage() {
  const router = useRouter();
  const user = useAuthStore((state) => state.user);

  const [template, setTemplate] = useState<TemplateDefinition | null>(null);
  const [templateMissing, setTemplateMissing] = useState(false);
  const [supplierTypes, setSupplierTypes] = useState<SupplierType[]>([]);
  const [supplierTypeId, setSupplierTypeId] = useState("");
  const [title, setTitle] = useState("");
  const [answers, setAnswers] = useState<TemplateAnswers>({});
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    getEffectiveTemplate("supplier_request")
      .then(setTemplate)
      .catch(() => {
        setTemplateMissing(true);
      });
    listSupplierTypes({ active_only: true, limit: 200 })
      .then((res) => setSupplierTypes(res.items.filter((t) => t.is_active)))
      .catch(() => setSupplierTypes([]));
  }, []);

  async function save(submit: boolean) {
    if (!user) return;
    if (!supplierTypeId) {
      setError("Supplier Type is required.");
      return;
    }
    setError(null);
    setLoading(true);
    try {
      const request = await createSupplierRequest({
        title,
        requestor_id: user.id,
        supplier_type_id: supplierTypeId,
        answers,
      });
      if (submit) {
        await transitionSupplierRequest(request.id, "submit");
      }
      router.replace("/dashboard/suppliers");
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="max-w-2xl space-y-6">
      <h1 className="text-2xl font-semibold">New Supplier Request</h1>
      {error && (
        <div className="card border border-red-200 bg-red-50 text-sm text-red-700">{error}</div>
      )}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void save(true);
        }}
        className="space-y-6"
      >
        <div className="card space-y-4">
          <div>
            <label className="label" htmlFor="title">
              Title <span className="text-red-500">*</span>
            </label>
            <input
              id="title"
              required
              className="input-field"
              placeholder="e.g. New packaging supplier for the Austin plant"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </div>
          <div>
            <label className="label" htmlFor="supplier_type">
              Supplier Type <span className="text-red-500">*</span>
            </label>
            <select
              id="supplier_type"
              required
              className="input-field"
              value={supplierTypeId}
              onChange={(e) => setSupplierTypeId(e.target.value)}
            >
              <option value="">Select a supplier type…</option>
              {supplierTypes.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name} ({t.code}) — {String(t.registration_mode).toUpperCase()}
                </option>
              ))}
            </select>
            {!supplierTypes.length && (
              <p className="mt-1 text-xs text-slate-500">
                No active supplier types found. Ask an admin to seed or create them under Admin →
                Supplier Types.
              </p>
            )}
          </div>
        </div>

        {template && (
          <DynamicTemplateForm
            template={template}
            answers={answers}
            onAnswersChange={setAnswers}
            disabled={loading}
          />
        )}
        {templateMissing && (
          <div className="card text-sm text-gray-500">
            No supplier request questionnaire is published for your organization; the request
            will be created with the title and supplier type only.
          </div>
        )}

        <div className="flex gap-3">
          <button
            type="submit"
            className="btn-primary"
            disabled={loading || !title || !supplierTypeId}
          >
            {loading ? "Saving..." : "Submit request"}
          </button>
          <button
            type="button"
            className="btn-secondary"
            disabled={loading || !title || !supplierTypeId}
            onClick={() => void save(false)}
          >
            Save draft
          </button>
        </div>
      </form>
    </div>
  );
}
