"use client";

import { Fragment, useEffect, useMemo, useState } from "react";
import {
  createTemplateAdmin,
  deleteTemplateAdmin,
  extractErrorMessage,
  getTemplateAdmin,
  listTemplatesAdmin,
  publishTemplateAdmin,
  updateTemplateAdmin,
} from "@/lib/api";
import { useAuthStore } from "@/lib/auth-store";
import {
  TEMPLATE_MODULES,
  TEMPLATE_QUESTION_TYPES,
  type TemplateDefinition,
  type TemplateDefinitionInput,
  type TemplateDefinitionSummary,
  type TemplateQuestionInput,
  type TemplateQuestionType,
  type TemplateScoringRule,
  type TemplateSectionInput,
  type TemplateVisibilityRule,
} from "@/lib/types";

// Local-only editor shapes: a stable client-side key for React list
// rendering/reordering, stripped back out to the plain payload shape
// (TemplateSectionInput/TemplateQuestionInput) before anything is sent to
// the API. Nothing here is persisted to the server as-is.
let keySeq = 0;
function nextKey(prefix: string) {
  keySeq += 1;
  return `${prefix}-${Date.now()}-${keySeq}`;
}

interface EditableQuestion extends TemplateQuestionInput {
  _key: string;
}
interface EditableSection extends TemplateSectionInput {
  _key: string;
  questions: EditableQuestion[];
}
interface EditableTemplate extends Omit<TemplateDefinitionInput, "sections"> {
  sections: EditableSection[];
}

function emptyForm(): EditableTemplate {
  return {
    module: "supplier_request",
    name: "",
    description: "",
    effective_date: "",
    expiry_date: "",
    inheritance_mode: "global",
    sections: [],
  };
}

function newQuestion(): EditableQuestion {
  return {
    _key: nextKey("q"),
    question_key: "",
    question_type: "text",
    question_text: "",
    help_text: "",
    placeholder: "",
    default_value: "",
    options: [],
    editable_flag: true,
    visible_flag: true,
    mandatory_flag: false,
    visibility_rule: null,
    scoring_rule: null,
    parent_question_key: null,
    order: 0,
  };
}

function newSection(): EditableSection {
  return {
    _key: nextKey("s"),
    name: "",
    order: 0,
    visibility_rule: null,
    mandatory_flag: false,
    questions: [],
  };
}

function slugify(text: string) {
  return text
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 100);
}

function toEditable(def: TemplateDefinition): EditableTemplate {
  return {
    module: def.module,
    name: def.name,
    description: def.description || "",
    effective_date: def.effective_date || "",
    expiry_date: def.expiry_date || "",
    inheritance_mode: def.inheritance_mode || "global",
    sections: def.sections.map((section) => ({
      _key: nextKey("s"),
      name: section.name,
      order: section.order,
      visibility_rule: section.visibility_rule ?? null,
      mandatory_flag: section.mandatory_flag,
      questions: section.questions.map((q) => ({
        _key: nextKey("q"),
        question_key: q.question_key,
        question_type: q.question_type,
        question_text: q.question_text,
        help_text: q.help_text || "",
        placeholder: q.placeholder || "",
        default_value: q.default_value || "",
        options: q.options || [],
        editable_flag: q.editable_flag,
        visible_flag: q.visible_flag,
        mandatory_flag: q.mandatory_flag,
        visibility_rule: q.visibility_rule ?? null,
        scoring_rule: q.scoring_rule ?? null,
        parent_question_key: q.parent_question_key ?? null,
        order: q.order,
      })),
    })),
  };
}

function toPayload(form: EditableTemplate): TemplateDefinitionInput {
  return {
    module: form.module,
    name: form.name,
    description: form.description || undefined,
    effective_date: form.effective_date || undefined,
    expiry_date: form.expiry_date || undefined,
    inheritance_mode: form.inheritance_mode,
    sections: form.sections.map((section, sIndex) => ({
      name: section.name,
      order: sIndex,
      visibility_rule: section.visibility_rule || null,
      mandatory_flag: section.mandatory_flag,
      questions: section.questions.map((q, qIndex) => ({
        question_key: q.question_key,
        question_type: q.question_type,
        question_text: q.question_text,
        help_text: q.help_text || undefined,
        placeholder: q.placeholder || undefined,
        default_value: q.default_value || undefined,
        options: q.options && q.options.length > 0 ? q.options : undefined,
        editable_flag: q.editable_flag,
        visible_flag: q.visible_flag,
        mandatory_flag: q.mandatory_flag,
        visibility_rule: q.visibility_rule || null,
        scoring_rule: q.scoring_rule || null,
        parent_question_key: q.parent_question_key || undefined,
        order: qIndex,
      })),
    })),
  };
}

type Selection = { sectionKey: string; questionKey: string | null } | null;

export default function TemplateAdminPage() {
  const user = useAuthStore((state) => state.user);
  const isAdmin = user?.role === "administrator" || user?.is_superuser === true;

  const [definitions, setDefinitions] = useState<TemplateDefinitionSummary[]>([]);
  const [moduleFilter, setModuleFilter] = useState<string>("all");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  const [form, setForm] = useState<EditableTemplate>(emptyForm());
  const [editingDraftId, setEditingDraftId] = useState<string | null>(null);
  const [sourceLabel, setSourceLabel] = useState<string | null>(null); // e.g. "editing v2 (draft)" / "new version of v3"
  const [selection, setSelection] = useState<Selection>(null);
  const [saving, setSaving] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setListError(null);
    try {
      const res = await listTemplatesAdmin({
        module: moduleFilter === "all" ? undefined : moduleFilter,
        status: statusFilter === "all" ? undefined : statusFilter,
      });
      setDefinitions(res.items);
    } catch (err) {
      setListError(extractErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [moduleFilter, statusFilter]);

  const groupedDefinitions = useMemo(() => {
    const groups = new Map<string, TemplateDefinitionSummary[]>();
    for (const def of definitions) {
      const key = `${def.module}::${def.name}`;
      const bucket = groups.get(key) ?? [];
      bucket.push(def);
      groups.set(key, bucket);
    }
    return Array.from(groups.entries())
      .map(([key, items]) => ({ key, items: [...items].sort((a, b) => b.version - a.version) }))
      .sort((a, b) => a.key.localeCompare(b.key));
  }, [definitions]);

  const allQuestionKeys = useMemo(
    () =>
      form.sections.flatMap((s) => s.questions.map((q) => q.question_key)).filter((k) => k.trim().length > 0),
    [form.sections]
  );

  function resetForm() {
    setForm(emptyForm());
    setEditingDraftId(null);
    setSourceLabel(null);
    setSelection(null);
    setFormError(null);
  }

  async function startNew() {
    resetForm();
  }

  async function startEditDraft(def: TemplateDefinitionSummary) {
    setFormError(null);
    try {
      const full = await getTemplateAdmin(def.id);
      setForm(toEditable(full));
      setEditingDraftId(full.status === "draft" ? full.id : null);
      setSourceLabel(full.status === "draft" ? `Editing draft v${full.version}` : `New version (from v${full.version})`);
      setSelection(null);
    } catch (err) {
      setFormError(extractErrorMessage(err));
    }
  }

  async function handleDelete(def: TemplateDefinitionSummary) {
    if (!confirm(`Delete draft "${def.name}" v${def.version}?`)) return;
    try {
      await deleteTemplateAdmin(def.id);
      if (editingDraftId === def.id) resetForm();
      await load();
    } catch (err) {
      setListError(extractErrorMessage(err));
    }
  }

  async function handlePublish(def: TemplateDefinitionSummary) {
    if (!confirm(`Publish "${def.name}" v${def.version}? This deprecates the currently published version, if any.`)) return;
    try {
      await publishTemplateAdmin(def.id);
      await load();
    } catch (err) {
      setListError(extractErrorMessage(err));
    }
  }

  function validateForm(): string[] {
    const errors: string[] = [];
    if (!form.name.trim()) errors.push("Name is required.");
    if (form.sections.length === 0) errors.push("Add at least one section.");
    form.sections.forEach((section, sIndex) => {
      if (!section.name.trim()) errors.push(`Section ${sIndex + 1}: name is required.`);
      if (section.questions.length === 0) errors.push(`Section "${section.name || sIndex + 1}": add at least one question.`);
      section.questions.forEach((q, qIndex) => {
        if (!q.question_key.trim()) errors.push(`Section "${section.name}", question ${qIndex + 1}: question key is required.`);
        if (!q.question_text.trim()) errors.push(`Section "${section.name}", question ${qIndex + 1}: question text is required.`);
      });
    });
    const seen = new Set<string>();
    for (const section of form.sections) {
      for (const q of section.questions) {
        if (!q.question_key) continue;
        if (seen.has(q.question_key)) errors.push(`Duplicate question key "${q.question_key}" -- keys must be unique across the whole template.`);
        seen.add(q.question_key);
      }
    }
    return errors;
  }

  async function handleSaveDraft() {
    setFormError(null);
    const errors = validateForm();
    if (errors.length > 0) {
      setFormError(errors.join(" \n"));
      return;
    }
    setSaving(true);
    try {
      const payload = toPayload(form);
      if (editingDraftId) {
        await updateTemplateAdmin(editingDraftId, payload);
      } else {
        const created = await createTemplateAdmin(payload);
        setEditingDraftId(created.id);
        setSourceLabel(`Editing draft v${created.version}`);
      }
      await load();
    } catch (err) {
      setFormError(extractErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  async function handlePublishCurrent() {
    if (!editingDraftId) {
      setFormError("Save as a draft first, then publish.");
      return;
    }
    setPublishing(true);
    setFormError(null);
    try {
      await publishTemplateAdmin(editingDraftId, form.effective_date || undefined);
      await load();
      resetForm();
    } catch (err) {
      setFormError(extractErrorMessage(err));
    } finally {
      setPublishing(false);
    }
  }

  // ---- section/question mutation helpers ----

  function updateSections(mutate: (sections: EditableSection[]) => EditableSection[]) {
    setForm((current) => ({ ...current, sections: mutate(current.sections) }));
  }

  function addSection() {
    updateSections((sections) => [...sections, newSection()]);
  }

  function removeSection(sectionKey: string) {
    updateSections((sections) => sections.filter((s) => s._key !== sectionKey));
    setSelection((sel) => (sel?.sectionKey === sectionKey ? null : sel));
  }

  function moveSection(sectionKey: string, direction: -1 | 1) {
    updateSections((sections) => {
      const index = sections.findIndex((s) => s._key === sectionKey);
      const target = index + direction;
      if (index < 0 || target < 0 || target >= sections.length) return sections;
      const next = [...sections];
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  }

  function patchSection(sectionKey: string, changes: Partial<EditableSection>) {
    updateSections((sections) => sections.map((s) => (s._key === sectionKey ? { ...s, ...changes } : s)));
  }

  function addQuestion(sectionKey: string) {
    updateSections((sections) =>
      sections.map((s) => (s._key === sectionKey ? { ...s, questions: [...s.questions, newQuestion()] } : s))
    );
  }

  function removeQuestion(sectionKey: string, questionKey: string) {
    updateSections((sections) =>
      sections.map((s) =>
        s._key === sectionKey ? { ...s, questions: s.questions.filter((q) => q._key !== questionKey) } : s
      )
    );
    setSelection((sel) => (sel?.questionKey === questionKey ? null : sel));
  }

  function moveQuestion(sectionKey: string, questionKey: string, direction: -1 | 1) {
    updateSections((sections) =>
      sections.map((s) => {
        if (s._key !== sectionKey) return s;
        const index = s.questions.findIndex((q) => q._key === questionKey);
        const target = index + direction;
        if (index < 0 || target < 0 || target >= s.questions.length) return s;
        const next = [...s.questions];
        [next[index], next[target]] = [next[target], next[index]];
        return { ...s, questions: next };
      })
    );
  }

  function patchQuestion(sectionKey: string, questionKey: string, changes: Partial<EditableQuestion>) {
    updateSections((sections) =>
      sections.map((s) =>
        s._key !== sectionKey
          ? s
          : { ...s, questions: s.questions.map((q) => (q._key === questionKey ? { ...q, ...changes } : q)) }
      )
    );
  }

  const selectedSection = form.sections.find((s) => s._key === selection?.sectionKey) || null;
  const selectedQuestion = selectedSection?.questions.find((q) => q._key === selection?.questionKey) || null;

  if (!isAdmin) {
    return (
      <div className="card">
        <p className="text-sm text-slate-600">Template administration is restricted to administrators.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Template Admin</h1>
          <p className="mt-1 text-sm text-slate-500">
            Author the dynamic questionnaires used across supplier requests, qualification, risk, performance,
            sourcing, and contracts.
          </p>
        </div>
        <button type="button" className="btn-primary" onClick={startNew}>
          + New Template
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <select className="input-field w-auto" value={moduleFilter} onChange={(e) => setModuleFilter(e.target.value)}>
          <option value="all">All modules</option>
          {TEMPLATE_MODULES.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </select>
        <select className="input-field w-auto" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="all">All statuses</option>
          <option value="draft">Draft</option>
          <option value="published">Published</option>
          <option value="deprecated">Deprecated</option>
        </select>
      </div>

      {listError && <p className="text-sm text-red-600">{listError}</p>}

      <div className="card overflow-x-auto p-0">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500">
            <tr>
              <th className="px-4 py-3">Name / module</th>
              <th className="px-4 py-3">Version</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Scope</th>
              <th className="px-4 py-3">Questions</th>
              <th className="px-4 py-3">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {loading && (
              <tr>
                <td className="px-4 py-4 text-slate-400" colSpan={6}>
                  Loading...
                </td>
              </tr>
            )}
            {!loading && definitions.length === 0 && (
              <tr>
                <td className="px-4 py-4 text-slate-400" colSpan={6}>
                  No templates yet -- create one below.
                </td>
              </tr>
            )}
            {groupedDefinitions.map((group) => {
              const [module, name] = group.key.split("::");
              return (
                <Fragment key={group.key}>
                  <tr className="bg-slate-50">
                    <td className="px-4 py-2 text-xs font-semibold uppercase text-slate-500" colSpan={6}>
                      {name} <span className="font-normal normal-case">({module})</span>
                      {group.items.length > 1 && (
                        <span className="ml-2 font-normal normal-case text-slate-400">{group.items.length} versions</span>
                      )}
                    </td>
                  </tr>
                  {group.items.map((def) => (
                    <tr key={def.id} className={`hover:bg-slate-50 ${editingDraftId === def.id ? "bg-blue-50" : ""}`}>
                      <td className="px-4 py-3">
                        <span className="text-slate-400">{def.description || "—"}</span>
                      </td>
                      <td className="px-4 py-3">v{def.version}</td>
                      <td className="px-4 py-3">
                        <span
                          className={`badge ${
                            def.status === "published"
                              ? "bg-green-100 text-green-700"
                              : def.status === "draft"
                              ? "bg-amber-100 text-amber-700"
                              : "bg-slate-100 text-slate-600"
                          }`}
                        >
                          {def.status}
                        </span>
                      </td>
                      <td className="px-4 py-3">{def.tenant_id ? "This tenant" : "Global (default)"}</td>
                      <td className="px-4 py-3">
                        {def.section_count} sections &middot; {def.question_count} questions
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex flex-wrap gap-3">
                          <button type="button" className="text-xs text-blue-600 hover:underline" onClick={() => startEditDraft(def)}>
                            {def.status === "draft" ? "Edit" : "New version"}
                          </button>
                          {def.status === "draft" && (
                            <button type="button" className="text-xs text-green-700 hover:underline" onClick={() => handlePublish(def)}>
                              Publish
                            </button>
                          )}
                          {def.status === "draft" && (
                            <button type="button" className="text-xs text-red-600 hover:underline" onClick={() => handleDelete(def)}>
                              Delete
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="card space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">{sourceLabel || "New template"}</h2>
          {(editingDraftId || form.name || form.sections.length > 0) && (
            <button type="button" className="btn-secondary" onClick={resetForm}>
              Cancel / start over
            </button>
          )}
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <label className="label">Module</label>
            <select
              className="input-field"
              value={form.module}
              onChange={(e) => setForm({ ...form, module: e.target.value })}
              disabled={!!editingDraftId}
            >
              {TEMPLATE_MODULES.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
            {editingDraftId && <p className="mt-1 text-xs text-slate-400">Module can't change once a draft exists -- start a new template instead.</p>}
          </div>
          <div>
            <label className="label">Name</label>
            <input
              className="input-field"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="e.g. Supplier Request (default)"
            />
          </div>
          <div className="md:col-span-2">
            <label className="label">Description</label>
            <textarea
              className="input-field"
              rows={2}
              value={form.description || ""}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
            />
          </div>
          <div>
            <label className="label">Effective date (optional)</label>
            <input
              type="date"
              className="input-field"
              value={form.effective_date || ""}
              onChange={(e) => setForm({ ...form, effective_date: e.target.value })}
            />
          </div>
          <div>
            <label className="label">Inheritance mode</label>
            <select
              className="input-field"
              value={form.inheritance_mode}
              onChange={(e) => setForm({ ...form, inheritance_mode: e.target.value })}
            >
              <option value="global">Global (available to every tenant unless overridden)</option>
              <option value="tenant">Tenant (overrides the global template)</option>
            </select>
          </div>
        </div>

        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-base font-semibold text-slate-900">Sections</h3>
            <button type="button" className="btn-secondary" onClick={addSection}>
              + Add section
            </button>
          </div>
          {form.sections.length === 0 && <p className="text-sm text-slate-400">No sections yet.</p>}
          <div className="space-y-3">
            {form.sections.map((section, sIndex) => (
              <div key={section._key} className="rounded-lg border border-slate-200">
                <div className="flex flex-wrap items-center gap-2 border-b border-slate-100 bg-slate-50 px-3 py-2">
                  <input
                    className="input-field flex-1 min-w-[180px]"
                    placeholder="Section name"
                    value={section.name}
                    onChange={(e) => patchSection(section._key, { name: e.target.value })}
                  />
                  <label className="flex items-center gap-1.5 text-xs text-slate-600">
                    <input
                      type="checkbox"
                      checked={section.mandatory_flag}
                      onChange={(e) => patchSection(section._key, { mandatory_flag: e.target.checked })}
                    />
                    Mandatory
                  </label>
                  <button
                    type="button"
                    className={`text-xs ${selection?.sectionKey === section._key && !selection?.questionKey ? "font-semibold text-brand-700" : "text-slate-500"}`}
                    onClick={() => setSelection({ sectionKey: section._key, questionKey: null })}
                  >
                    Visibility rule{section.visibility_rule ? " *" : ""}
                  </button>
                  <div className="ml-auto flex items-center gap-2">
                    <button type="button" className="text-xs text-slate-500 hover:text-slate-800" disabled={sIndex === 0} onClick={() => moveSection(section._key, -1)}>
                      ↑
                    </button>
                    <button type="button" className="text-xs text-slate-500 hover:text-slate-800" disabled={sIndex === form.sections.length - 1} onClick={() => moveSection(section._key, 1)}>
                      ↓
                    </button>
                    <button type="button" className="text-xs text-red-600 hover:underline" onClick={() => removeSection(section._key)}>
                      Remove section
                    </button>
                  </div>
                </div>
                <div className="space-y-2 p-3">
                  {section.questions.map((q, qIndex) => (
                    <div
                      key={q._key}
                      className={`flex flex-wrap items-center gap-2 rounded-md border px-3 py-2 ${
                        selection?.questionKey === q._key ? "border-brand-400 bg-brand-50" : "border-slate-200"
                      }`}
                    >
                      <span className="badge bg-slate-100 text-slate-600">{q.question_type}</span>
                      <input
                        className="input-field flex-1 min-w-[160px]"
                        placeholder="Question text"
                        value={q.question_text}
                        onChange={(e) => {
                          const changes: Partial<EditableQuestion> = { question_text: e.target.value };
                          if (!q.question_key) changes.question_key = slugify(e.target.value);
                          patchQuestion(section._key, q._key, changes);
                        }}
                      />
                      <input
                        className="input-field w-40"
                        placeholder="question_key"
                        value={q.question_key}
                        onChange={(e) => patchQuestion(section._key, q._key, { question_key: slugify(e.target.value) })}
                      />
                      {q.mandatory_flag && <span className="badge bg-red-50 text-red-600">required</span>}
                      {q.scoring_rule && <span className="badge bg-purple-50 text-purple-600">scored</span>}
                      {q.visibility_rule && <span className="badge bg-blue-50 text-blue-600">conditional</span>}
                      <div className="ml-auto flex items-center gap-2">
                        <button type="button" className="text-xs text-slate-500 hover:text-slate-800" disabled={qIndex === 0} onClick={() => moveQuestion(section._key, q._key, -1)}>
                          ↑
                        </button>
                        <button
                          type="button"
                          className="text-xs text-slate-500 hover:text-slate-800"
                          disabled={qIndex === section.questions.length - 1}
                          onClick={() => moveQuestion(section._key, q._key, 1)}
                        >
                          ↓
                        </button>
                        <button
                          type="button"
                          className="text-xs text-blue-600 hover:underline"
                          onClick={() => setSelection({ sectionKey: section._key, questionKey: q._key })}
                        >
                          Edit
                        </button>
                        <button type="button" className="text-xs text-red-600 hover:underline" onClick={() => removeQuestion(section._key, q._key)}>
                          Remove
                        </button>
                      </div>
                    </div>
                  ))}
                  <button type="button" className="btn-secondary" onClick={() => addQuestion(section._key)}>
                    + Add question
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Docked inspector: editing a question's full field set, or a
            section's visibility rule when questionKey is null. */}
        {selection && selectedSection && (
          <div className="rounded-lg border border-slate-200 bg-slate-50">
            <div className="flex items-center justify-between border-b border-slate-200 bg-white px-4 py-2.5">
              <span className="text-sm font-semibold text-slate-700">
                {selectedQuestion ? `Question: ${selectedQuestion.question_text || "(untitled)"}` : `Section rule: ${selectedSection.name || "(untitled)"}`}
              </span>
              <button type="button" className="text-xs text-slate-500 hover:text-slate-700" onClick={() => setSelection(null)}>
                Close
              </button>
            </div>
            <div className="max-h-[560px] overflow-y-auto p-4">
              {selectedQuestion ? (
                <QuestionInspector
                  key={selectedQuestion._key}
                  question={selectedQuestion}
                  otherKeys={allQuestionKeys.filter((k) => k !== selectedQuestion.question_key)}
                  onUpdate={(changes) => patchQuestion(selectedSection._key, selectedQuestion._key, changes)}
                />
              ) : (
                <div className="max-w-xl" key={selectedSection._key}>
                  <p className="mb-2 text-sm text-slate-500">Controls whether this whole section is shown, based on answers to earlier questions.</p>
                  <VisibilityRuleEditor
                    value={selectedSection.visibility_rule || null}
                    fieldOptions={allQuestionKeys}
                    onChange={(rule) => patchSection(selectedSection._key, { visibility_rule: rule })}
                  />
                </div>
              )}
            </div>
          </div>
        )}

        {formError && <p className="whitespace-pre-line text-sm text-red-600">{formError}</p>}
        <div className="flex flex-wrap gap-3">
          <button type="button" disabled={saving} className="btn-primary" onClick={handleSaveDraft}>
            {saving ? "Saving..." : editingDraftId ? "Save draft" : "Create draft"}
          </button>
          <button type="button" disabled={publishing || !editingDraftId} className="btn-secondary" onClick={handlePublishCurrent}>
            {publishing ? "Publishing..." : "Publish"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---- Question inspector ----

function QuestionInspector({
  question,
  otherKeys,
  onUpdate,
}: {
  question: EditableQuestion;
  otherKeys: string[];
  onUpdate: (changes: Partial<EditableQuestion>) => void;
}) {
  const needsOptions = question.question_type === "dropdown" || question.question_type === "multiselect";

  return (
    <div className="space-y-4">
      <div className="grid gap-3 md:grid-cols-2">
        <div>
          <label className="label">Question type</label>
          <select
            className="input-field"
            value={question.question_type}
            onChange={(e) => onUpdate({ question_type: e.target.value as TemplateQuestionType })}
          >
            {TEMPLATE_QUESTION_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="label">Question key (stable, machine-readable)</label>
          <input className="input-field" value={question.question_key} onChange={(e) => onUpdate({ question_key: slugify(e.target.value) })} />
        </div>
        <div className="md:col-span-2">
          <label className="label">Question text</label>
          <input className="input-field" value={question.question_text} onChange={(e) => onUpdate({ question_text: e.target.value })} />
        </div>
        <div>
          <label className="label">Help text (optional)</label>
          <input className="input-field" value={question.help_text || ""} onChange={(e) => onUpdate({ help_text: e.target.value })} />
        </div>
        <div>
          <label className="label">Placeholder (optional)</label>
          <input className="input-field" value={question.placeholder || ""} onChange={(e) => onUpdate({ placeholder: e.target.value })} />
        </div>
        <div>
          <label className="label">Default value (optional)</label>
          <input className="input-field" value={question.default_value || ""} onChange={(e) => onUpdate({ default_value: e.target.value })} />
        </div>
        {needsOptions && (
          <div className="md:col-span-2">
            <label className="label">Options (comma-separated)</label>
            <input
              className="input-field"
              value={(question.options || []).join(", ")}
              onChange={(e) =>
                onUpdate({
                  options: e.target.value
                    .split(",")
                    .map((v) => v.trim())
                    .filter(Boolean),
                })
              }
            />
          </div>
        )}
        <div>
          <label className="label">Depends on (optional parent question key)</label>
          <select
            className="input-field"
            value={question.parent_question_key || ""}
            onChange={(e) => onUpdate({ parent_question_key: e.target.value || null })}
          >
            <option value="">None</option>
            {otherKeys.map((k) => (
              <option key={k} value={k}>
                {k}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="flex flex-wrap gap-4">
        <label className="flex items-center gap-1.5 text-sm text-slate-600">
          <input type="checkbox" checked={question.mandatory_flag} onChange={(e) => onUpdate({ mandatory_flag: e.target.checked })} />
          Mandatory when visible
        </label>
        <label className="flex items-center gap-1.5 text-sm text-slate-600">
          <input type="checkbox" checked={question.editable_flag} onChange={(e) => onUpdate({ editable_flag: e.target.checked })} />
          Editable by respondent
        </label>
        <label className="flex items-center gap-1.5 text-sm text-slate-600">
          <input type="checkbox" checked={question.visible_flag} onChange={(e) => onUpdate({ visible_flag: e.target.checked })} />
          Enabled (unchecking hides it everywhere, regardless of the rule below)
        </label>
      </div>

      <div className="border-t border-slate-200 pt-3">
        <h4 className="mb-2 text-sm font-semibold text-slate-700">Visibility rule</h4>
        <p className="mb-2 text-xs text-slate-500">Show this question only when a condition on an earlier answer is met. Leave empty to always show it.</p>
        <VisibilityRuleEditor value={question.visibility_rule || null} fieldOptions={otherKeys} onChange={(rule) => onUpdate({ visibility_rule: rule })} />
      </div>

      <div className="border-t border-slate-200 pt-3">
        <h4 className="mb-2 text-sm font-semibold text-slate-700">Scoring rule</h4>
        <p className="mb-2 text-xs text-slate-500">Contributes to the response's weighted 0-100 score. Leave unscored if this question shouldn't affect scoring.</p>
        <ScoringRuleEditor value={question.scoring_rule || null} onChange={(rule) => onUpdate({ scoring_rule: rule })} />
      </div>
    </div>
  );
}

// ---- Visibility rule editor: simple field/op/value picker, with a raw-JSON
// escape hatch for all/any groups (mirrors the workflow designer's
// show-raw-JSON pattern for anything the guided UI doesn't cover). ----

const VISIBILITY_OPS: { value: NonNullable<TemplateVisibilityRule["op"]>; label: string }[] = [
  { value: "eq", label: "equals" },
  { value: "neq", label: "does not equal" },
  { value: "gt", label: "> greater than" },
  { value: "gte", label: ">= at least" },
  { value: "lt", label: "< less than" },
  { value: "lte", label: "<= at most" },
  { value: "in", label: "is one of" },
];

function isSimpleCondition(rule: TemplateVisibilityRule | null): boolean {
  return !!rule && !rule.all && !rule.any;
}

function VisibilityRuleEditor({
  value,
  fieldOptions,
  onChange,
}: {
  value: TemplateVisibilityRule | null;
  fieldOptions: string[];
  onChange: (rule: TemplateVisibilityRule | null) => void;
}) {
  const [showJson, setShowJson] = useState(false);
  const [jsonText, setJsonText] = useState(value ? JSON.stringify(value, null, 2) : "");
  const [jsonError, setJsonError] = useState<string | null>(null);

  const isGroup = !!value && (value.all || value.any);

  if (showJson || isGroup) {
    return (
      <div className="space-y-2">
        <textarea
          className="input-field font-mono text-xs"
          rows={6}
          value={jsonText || (value ? JSON.stringify(value, null, 2) : "")}
          onChange={(e) => {
            setJsonText(e.target.value);
            try {
              const parsed = e.target.value.trim() ? JSON.parse(e.target.value) : null;
              onChange(parsed);
              setJsonError(null);
            } catch {
              setJsonError("Invalid JSON -- not saved until this is valid.");
            }
          }}
          placeholder='{"field": "question_key", "op": "eq", "value": "yes"} or {"all": [...]} / {"any": [...]}'
        />
        {jsonError && <p className="text-xs text-red-600">{jsonError}</p>}
        <button
          type="button"
          className="text-xs text-blue-600 hover:underline"
          onClick={() => {
            setShowJson(false);
            setJsonText("");
            onChange(null);
          }}
        >
          Clear and use the guided editor
        </button>
      </div>
    );
  }

  const condition = isSimpleCondition(value) ? value! : null;

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <select
          className="input-field w-auto min-w-[140px]"
          value={condition?.field || ""}
          onChange={(e) => onChange(e.target.value ? { field: e.target.value, op: condition?.op || "eq", value: condition?.value ?? "" } : null)}
        >
          <option value="">No condition (always visible)</option>
          {fieldOptions.map((k) => (
            <option key={k} value={k}>
              {k}
            </option>
          ))}
        </select>
        {condition && (
          <>
            <select
              className="input-field w-auto"
              value={condition.op || "eq"}
              onChange={(e) => onChange({ ...condition, op: e.target.value as TemplateVisibilityRule["op"] })}
            >
              {VISIBILITY_OPS.map((op) => (
                <option key={op.value} value={op.value}>
                  {op.label}
                </option>
              ))}
            </select>
            <input
              className="input-field w-auto min-w-[140px]"
              placeholder="value"
              value={typeof condition.value === "string" || typeof condition.value === "number" ? String(condition.value) : ""}
              onChange={(e) => onChange({ ...condition, value: e.target.value })}
            />
          </>
        )}
      </div>
      <button type="button" className="text-xs text-slate-500 hover:text-slate-800" onClick={() => setShowJson(true)}>
        Advanced: edit as JSON (needed for "all"/"any" groups)
      </button>
    </div>
  );
}

// ---- Scoring rule editor ----

type ScoringMode = "none" | "map" | "threshold" | "present";

function scoringMode(rule: TemplateScoringRule | null): ScoringMode {
  if (!rule) return "none";
  if (rule.map) return "map";
  if (rule.threshold !== undefined) return "threshold";
  if (rule.present !== undefined) return "present";
  return "none";
}

function ScoringRuleEditor({ value, onChange }: { value: TemplateScoringRule | null; onChange: (rule: TemplateScoringRule | null) => void }) {
  const mode = scoringMode(value);
  const weight = value?.weight ?? 10;

  function setMode(next: ScoringMode) {
    if (next === "none") {
      onChange(null);
      return;
    }
    if (next === "map") onChange({ weight, map: value?.map || {} });
    if (next === "threshold") onChange({ weight, threshold: value?.threshold ?? 0, above: value?.above ?? 10, below: value?.below ?? 0 });
    if (next === "present") onChange({ weight, present: value?.present ?? 10 });
  }

  const mapEntries = Object.entries(value?.map || {});

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <select className="input-field w-auto" value={mode} onChange={(e) => setMode(e.target.value as ScoringMode)}>
          <option value="none">Not scored</option>
          <option value="map">Map answer -&gt; score (choice/yes-no questions)</option>
          <option value="threshold">Numeric threshold</option>
          <option value="present">Any answer given (completeness)</option>
        </select>
        {mode !== "none" && (
          <label className="flex items-center gap-1.5 text-sm text-slate-600">
            Weight
            <input
              type="number"
              min={1}
              max={100}
              className="input-field w-20"
              value={weight}
              onChange={(e) => onChange({ ...(value as TemplateScoringRule), weight: Number(e.target.value) })}
            />
          </label>
        )}
      </div>

      {mode === "map" && (
        <div className="space-y-1.5">
          {mapEntries.map(([answer, score], idx) => (
            <div key={idx} className="flex items-center gap-2">
              <input
                className="input-field w-40"
                placeholder="answer (e.g. yes)"
                value={answer}
                onChange={(e) => {
                  const nextMap = { ...(value?.map || {}) };
                  delete nextMap[answer];
                  nextMap[e.target.value] = score;
                  onChange({ ...(value as TemplateScoringRule), map: nextMap });
                }}
              />
              <input
                type="number"
                min={0}
                max={10}
                className="input-field w-20"
                value={score}
                onChange={(e) => {
                  const nextMap = { ...(value?.map || {}) };
                  nextMap[answer] = Number(e.target.value);
                  onChange({ ...(value as TemplateScoringRule), map: nextMap });
                }}
              />
              <button
                type="button"
                className="text-xs text-red-600 hover:underline"
                onClick={() => {
                  const nextMap = { ...(value?.map || {}) };
                  delete nextMap[answer];
                  onChange({ ...(value as TemplateScoringRule), map: nextMap });
                }}
              >
                Remove
              </button>
            </div>
          ))}
          <button
            type="button"
            className="text-xs text-blue-600 hover:underline"
            onClick={() => onChange({ ...(value as TemplateScoringRule), map: { ...(value?.map || {}), "": 0 } })}
          >
            + Add answer -&gt; score row
          </button>
        </div>
      )}

      {mode === "threshold" && (
        <div className="flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-1.5 text-sm text-slate-600">
            Threshold
            <input
              type="number"
              className="input-field w-24"
              value={value?.threshold ?? 0}
              onChange={(e) => onChange({ ...(value as TemplateScoringRule), threshold: Number(e.target.value) })}
            />
          </label>
          <label className="flex items-center gap-1.5 text-sm text-slate-600">
            Score if &gt;=
            <input
              type="number"
              min={0}
              max={10}
              className="input-field w-20"
              value={value?.above ?? 10}
              onChange={(e) => onChange({ ...(value as TemplateScoringRule), above: Number(e.target.value) })}
            />
          </label>
          <label className="flex items-center gap-1.5 text-sm text-slate-600">
            Score if below
            <input
              type="number"
              min={0}
              max={10}
              className="input-field w-20"
              value={value?.below ?? 0}
              onChange={(e) => onChange({ ...(value as TemplateScoringRule), below: Number(e.target.value) })}
            />
          </label>
        </div>
      )}

      {mode === "present" && (
        <label className="flex items-center gap-1.5 text-sm text-slate-600">
          Score if answered
          <input
            type="number"
            min={0}
            max={10}
            className="input-field w-20"
            value={value?.present ?? 10}
            onChange={(e) => onChange({ ...(value as TemplateScoringRule), present: Number(e.target.value) })}
          />
        </label>
      )}
    </div>
  );
}
