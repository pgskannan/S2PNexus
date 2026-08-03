"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import DynamicTemplateForm from "@/components/DynamicTemplateForm";
import {
  createSupplierRequest,
  extractErrorMessage,
  getEffectiveTemplate,
  transitionSupplierRequest,
} from "@/lib/api";
import { useAuthStore } from "@/lib/auth-store";
import type { TemplateAnswers, TemplateDefinition } from "@/lib/types";

export default function NewSupplierRequestPage() {
  const router = useRouter();
  const user = useAuthStore((state) => state.user);

  const [template, setTemplate] = useState<TemplateDefinition | null>(null);
  const [templateMissing, setTemplateMissing] = useState(false);
  const [title, setTitle] = useState("");
  const [answers, setAnswers] = useState<TemplateAnswers>({});
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    getEffectiveTemplate("supplier_request")
      .then(setTemplate)
      .catch(() => {
        // No published template: page still works, questionnaire section is
        // simply absent (legacy fixed-column behavior on the backend).
        setTemplateMissing(true);
      });
  }, []);

  async function save(submit: boolean) {
    if (!user) return;
    setError(null);
    setLoading(true);
    try {
      const request = await createSupplierRequest({
        title,
        requestor_id: user.id,
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
            will be created with the title only.
          </div>
        )}

        <div className="flex gap-3">
          <button type="submit" className="btn-primary" disabled={loading || !title}>
            {loading ? "Saving..." : "Submit request"}
          </button>
          <button
            type="button"
            className="btn-secondary"
            disabled={loading || !title}
            onClick={() => void save(false)}
          >
            Save draft
          </button>
        </div>
      </form>
    </div>
  );
}
