"""Validate backend/app/templates/email/templates_catalog.json completeness."""

from pathlib import Path

import json

CATALOG = Path(__file__).resolve().parent.parent / "backend" / "app" / "templates" / "email" / "templates_catalog.json"

REQUIRED_KEYS = ["id", "module", "subject", "html", "text", "variables", "tenant_overridable", "version", "email_type", "redirectable"]
BRANDING = ["{{tenant.logo}}", "{{tenant.name}}", "{{tenant.footer}}", "{{tenant.disclaimer}}", "{{i18n.en}}", "{{i18n.fr}}", "{{i18n.es}}"]


def main() -> None:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    errors: list[str] = []
    for t in catalog:
        tid = t.get("id", "?")
        for k in REQUIRED_KEYS:
            if k not in t:
                errors.append(f"{tid}: missing key {k}")
        html, text = t.get("html", ""), t.get("text", "")
        if not html.lstrip().startswith("<!DOCTYPE html>") or not html.rstrip().endswith("</html>"):
            errors.append(f"{tid}: malformed html wrapper")
        if not text.strip():
            errors.append(f"{tid}: empty text version")
        for b in BRANDING:
            if b not in html:
                errors.append(f"{tid}: missing {b} in html")
        unused = [v for v in t.get("variables", []) if v not in html and v not in text]
        if unused:
            errors.append(f"{tid}: variables listed but unused -> {unused}")
        if not isinstance(t.get("tenant_overridable"), bool):
            errors.append(f"{tid}: tenant_overridable not bool")
        if not isinstance(t.get("redirectable"), bool):
            errors.append(f"{tid}: redirectable not bool")

    print(f"total templates: {len(catalog)}")
    print(f"errors: {len(errors)}")
    for e in errors[:40]:
        print(" -", e)
    print("ids:", ", ".join(t["id"] for t in catalog))
    print("modules:", ", ".join(sorted({t["module"] for t in catalog})))
    print("non-redirectable:", ", ".join(t["id"] for t in catalog if not t["redirectable"]))
    raise SystemExit(1 if errors else 0)


if __name__ == "__main__":
    main()
