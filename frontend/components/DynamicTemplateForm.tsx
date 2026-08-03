"use client";

/**
 * Generic renderer for a Universal Template Framework questionnaire.
 *
 * Deliberately module-agnostic: no supplier-request (or any other document
 * type) field names appear here. Point it at any TemplateDefinition from
 * GET /templates/{module}/effective and it renders sections/questions and
 * re-evaluates visibility on every answer change.
 *
 * evaluateVisibility mirrors backend/app/services/template_engine.py's
 * evaluate_visibility EXACTLY -- same grammar, same semantics (neq passes
 * when unanswered, ordering ops coerce numeric strings, unknown ops fail
 * closed). If you change one, change both.
 */

import type {
  TemplateAnswers,
  TemplateDefinition,
  TemplateQuestion,
  TemplateSection,
  TemplateVisibilityRule,
} from "@/lib/types";

const ORDERING_OPS = new Set(["gt", "gte", "lt", "lte"]);

function coerceNumeric(value: unknown): number | unknown {
  if (value === null || value === undefined || typeof value === "boolean") return value;
  if (typeof value === "number") return value;
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    if (!Number.isNaN(parsed)) return parsed;
  }
  return value;
}

export function evaluateVisibility(
  rule: TemplateVisibilityRule | null | undefined,
  answers: TemplateAnswers
): boolean {
  if (!rule || Object.keys(rule).length === 0) return true;

  if (rule.all) return rule.all.every((child) => evaluateVisibility(child, answers));
  if (rule.any) return rule.any.some((child) => evaluateVisibility(child, answers));

  const op = rule.op ?? "eq";
  const actual = rule.field !== undefined ? answers[rule.field] : undefined;
  const expected = rule.value;
  const missing = actual === undefined || actual === null;

  if (op === "neq") return missing ? true : actual !== expected;
  if (missing) return false;
  if (op === "eq") return actual === expected;
  if (op === "in") {
    const expectedItems = Array.isArray(expected) ? expected : [expected];
    if (Array.isArray(actual)) return actual.some((item) => expectedItems.includes(item));
    return expectedItems.includes(actual);
  }
  if (ORDERING_OPS.has(op)) {
    const left = coerceNumeric(actual);
    const right = coerceNumeric(expected);
    if (typeof left !== "number" || typeof right !== "number") return false; // fail closed
    if (op === "gt") return left > right;
    if (op === "gte") return left >= right;
    if (op === "lt") return left < right;
    return left <= right;
  }
  return false; // unknown operator: fail closed, same as the backend
}

function QuestionField({
  question,
  value,
  onChange,
  disabled,
}: {
  question: TemplateQuestion;
  value: unknown;
  onChange: (value: unknown) => void;
  disabled?: boolean;
}) {
  const common = {
    id: question.question_key,
    disabled: disabled || !question.editable_flag,
    required: question.mandatory_flag,
  };
  const stringValue = value === undefined || value === null ? "" : String(value);

  switch (question.question_type) {
    case "textarea":
      return (
        <textarea
          {...common}
          className="input-field min-h-24"
          placeholder={question.placeholder ?? undefined}
          value={stringValue}
          onChange={(e) => onChange(e.target.value)}
        />
      );
    case "numeric":
      return (
        <input
          {...common}
          type="number"
          className="input-field"
          placeholder={question.placeholder ?? undefined}
          value={stringValue}
          onChange={(e) => onChange(e.target.value)}
        />
      );
    case "date":
      return (
        <input
          {...common}
          type="date"
          className="input-field"
          value={stringValue}
          onChange={(e) => onChange(e.target.value)}
        />
      );
    case "yes_no":
      return (
        <div className="flex gap-4">
          {["yes", "no"].map((option) => (
            <label key={option} className="flex items-center gap-2 text-sm">
              <input
                type="radio"
                name={question.question_key}
                disabled={common.disabled}
                checked={stringValue === option}
                onChange={() => onChange(option)}
              />
              {option === "yes" ? "Yes" : "No"}
            </label>
          ))}
        </div>
      );
    case "dropdown":
      return (
        <select
          {...common}
          className="input-field"
          value={stringValue}
          onChange={(e) => onChange(e.target.value)}
        >
          <option value="">Select...</option>
          {(question.options ?? []).map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      );
    case "multiselect": {
      const selected = Array.isArray(value) ? (value as string[]) : [];
      return (
        <div className="space-y-1">
          {(question.options ?? []).map((option) => (
            <label key={option} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                disabled={common.disabled}
                checked={selected.includes(option)}
                onChange={(e) =>
                  onChange(
                    e.target.checked
                      ? [...selected, option]
                      : selected.filter((item) => item !== option)
                  )
                }
              />
              {option}
            </label>
          ))}
        </div>
      );
    }
    case "file_upload":
      // This batch stores the file NAME as the answer (upload plumbing is a
      // follow-up); mandatory/conditional semantics still work end to end.
      return (
        <input
          {...common}
          type="file"
          className="input-field"
          onChange={(e) => onChange(e.target.files?.[0]?.name ?? "")}
        />
      );
    case "text":
      return (
        <input
          {...common}
          type="text"
          className="input-field"
          placeholder={question.placeholder ?? undefined}
          value={stringValue}
          onChange={(e) => onChange(e.target.value)}
        />
      );
    default:
      // Reserved/unimplemented question types (table_grid, kpi_input,
      // clause_selector, ai_generated) fail loudly, mirroring the backend.
      return (
        <p className="text-sm text-red-600">
          Unsupported question type: {question.question_type}
        </p>
      );
  }
}

export default function DynamicTemplateForm({
  template,
  answers,
  onAnswersChange,
  disabled,
}: {
  template: TemplateDefinition;
  answers: TemplateAnswers;
  onAnswersChange: (answers: TemplateAnswers) => void;
  disabled?: boolean;
}) {
  const setAnswer = (key: string, value: unknown) =>
    onAnswersChange({ ...answers, [key]: value });

  const visibleSections = template.sections.filter((section: TemplateSection) =>
    evaluateVisibility(section.visibility_rule, answers)
  );

  return (
    <div className="space-y-6">
      {visibleSections.map((section) => {
        const visibleQuestions = section.questions.filter(
          (question) =>
            question.visible_flag && evaluateVisibility(question.visibility_rule, answers)
        );
        if (visibleQuestions.length === 0) return null;
        return (
          <div key={section.id} className="card space-y-4">
            <h2 className="text-lg font-medium">{section.name}</h2>
            {visibleQuestions.map((question) => (
              <div key={question.id}>
                <label className="label" htmlFor={question.question_key}>
                  {question.question_text}
                  {question.mandatory_flag && <span className="text-red-500"> *</span>}
                </label>
                {question.help_text && (
                  <p className="mb-1 text-xs text-gray-500">{question.help_text}</p>
                )}
                <QuestionField
                  question={question}
                  value={answers[question.question_key]}
                  onChange={(value) => setAnswer(question.question_key, value)}
                  disabled={disabled}
                />
              </div>
            ))}
          </div>
        );
      })}
    </div>
  );
}
