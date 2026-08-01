"""S2PNexus S2P Email Template Catalog generator.

Builds `backend/app/templates/email/templates_catalog.json` — a complete,
versioned catalog of enterprise S2P notification email templates (SAP
Ariba-style workflow notifications).

Design rules:
  * Handlebars-style variables: {{var}}, {{#each}} / {{/each}}, {{#if}} / {{/if}}
  * Tenant branding blocks:   {{tenant.logo}}, {{tenant.name}},
                              {{tenant.footer}}, {{tenant.disclaimer}}
  * Multi-language hooks:     {{i18n.en}}, {{i18n.fr}}, {{i18n.es}}
  * Redirect classification:  `redirectable` is FALSE only for welcome,
                              password reset and order confirmation
                              (Email Redirect spec, Section 1).
  * Versioning:               each template carries a `version` field
                              (v1; v2/v3 as overrides).

Usage:
    c:/S2PNexus/.venv/Scripts/python.exe scripts/generate_email_templates.py
"""

from __future__ import annotations

import json
from pathlib import Path

OUTPUT = Path(__file__).resolve().parent.parent / "backend" / "app" / "templates" / "email" / "templates_catalog.json"

# ---------------------------------------------------------------------------
# Enterprise HTML shell (navy/gold design system, email-safe, mobile + dark)
# ---------------------------------------------------------------------------
_SHELL = """<!DOCTYPE html>
<html lang="en" xmlns="http://www.w3.org/1999/xhtml">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<meta name="x-apple-disable-message-reformatting"/>
<title>__SUBJECT__</title>
<style type="text/css">
*{margin:0;padding:0;box-sizing:border-box}
body,table,td,a{-webkit-text-size-adjust:100%;-ms-text-size-adjust:100%}
table,td{mso-table-lspace:0pt;mso-table-rspace:0pt;border-collapse:collapse}
img{-ms-interpolation-mode:bicubic;border:0;height:auto;line-height:100%;outline:none;text-decoration:none}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif}
.btn{display:inline-block;border-radius:6px}
a:hover,.btn:hover{filter:brightness(0.94)}
@media (prefers-color-scheme:dark){
.body-bg{background-color:#0d1b2a !important}
.card{background-color:#152238 !important}
.card-border{border:1px solid #24344d !important}
.text-primary{color:#f3f6fb !important}
.text-secondary{color:#b9c6d8 !important}
.hairline{background-color:#24344d !important}
}
@media only screen and (max-width:600px){
.container{width:100% !important;max-width:100% !important}
.stack{display:block !important;width:100% !important}
.btn-cell{display:block !important;width:100% !important;text-align:center !important}
.btn{display:block !important;width:100% !important;padding:16px 24px !important;box-sizing:border-box}
.px{padding-left:20px !important;padding-right:20px !important}
.h1{font-size:24px !important;line-height:30px !important}
.hide-mobile{display:none !important}
}
@media only screen and (max-width:400px){.px{padding-left:16px !important;padding-right:16px !important}}
</style>
</head>
<body class="body-bg" style="margin:0;padding:0;background-color:#f4f6f8;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;">
<div style="display:none;max-height:0;overflow:hidden;mso-hide:all;">__PREHEADER__</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#f4f6f8;">
<tr><td align="center" style="padding:32px 16px;">
<table class="container" role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" style="width:600px;max-width:600px;background-color:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(15,42,67,0.08);">
<tr><td style="background:linear-gradient(135deg,#0f2a43 0%,#1e3a5f 100%);padding:28px 40px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
<tr>
<td align="left">
<table role="presentation" cellpadding="0" cellspacing="0" border="0">
<tr>
<td style="padding:0 10px 0 0;"><img src="{{tenant.logo}}" alt="{{tenant.name}}" width="34" height="34" style="display:block;width:34px;height:34px;border-radius:6px;"/></td>
<td style="font-size:20px;font-weight:700;color:#ffffff;letter-spacing:0.4px;">{{tenant.name}}</td>
</tr>
</table>
</td>
<td align="right" class="stack" style="text-align:right;">
<p style="margin:0;font-size:12px;color:#9fb4cc;letter-spacing:0.3px;">__MODULE__</p>
</td>
</tr>
</table>
</td></tr>
__BODY__
<tr><td class="px" style="padding:24px 40px 0 40px;">
<table class="hairline" role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="height:1px;background-color:#e3e8ee;"><tr><td style="height:1px;line-height:1px;">&nbsp;</td></tr></table>
</td></tr>
<tr><td style="background-color:#f8fafc;padding:24px 40px;border-top:1px solid #e3e8ee;">
<p style="margin:0 0 6px 0;font-size:12px;color:#8a97a5;line-height:1.6;">{{tenant.footer}}</p>
<p style="margin:0 0 6px 0;font-size:11px;color:#8a97a5;line-height:1.5;">{{tenant.disclaimer}}</p>
<p class="text-secondary" style="margin:10px 0 0 0;font-size:11px;color:#8a97a5;">Language: {{i18n.en}} &middot; {{i18n.fr}} &middot; {{i18n.es}}</p>
<p style="margin:6px 0 0 0;font-size:11px;color:#8a97a5;">&copy; {{year}} {{tenant.name}}. All rights reserved.</p>
</td></tr>
</table>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
<tr><td align="center" style="padding:14px 16px 0 16px;">
<p style="margin:0;font-size:11px;color:#8a97a5;">This is a system-generated message from {{tenant.name}}. Please do not reply to this email.</p>
</td></tr>
</table>
</td></tr>
</table>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Body helpers (return raw HTML; handlebars stays literal)
# ---------------------------------------------------------------------------
def hero(title: str, subtitle: str) -> str:
    return (
        '<tr><td class="px" style="padding:32px 40px 8px 40px;">'
        f'<h1 class="h1 text-primary" style="margin:0 0 12px 0;font-size:26px;line-height:32px;font-weight:700;color:#0f2a43;">{title}</h1>'
        f'<p class="text-secondary" style="margin:0;font-size:16px;line-height:1.6;color:#5b6770;">{subtitle}</p>'
        "</td></tr>"
    )


def card(title: str, *rows: tuple[str, str]) -> str:
    cells = "".join(
        '<tr>'
        f'<td class="text-secondary" style="padding:4px 0;font-size:14px;color:#5b6770;width:45%;">{k}</td>'
        f'<td class="text-primary" style="padding:4px 0;font-size:14px;font-weight:600;color:#0f2a43;">{v}</td>'
        "</tr>"
        for k, v in rows
    )
    return (
        '<tr><td class="px" style="padding:24px 40px 8px 40px;">'
        '<table class="card card-border" role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#f8fafc;border:1px solid #e3e8ee;border-radius:8px;">'
        '<tr><td style="padding:20px 24px;">'
        f'<p style="margin:0 0 12px 0;font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:#c9a227;">{title}</p>'
        f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">{cells}</table>'
        "</td></tr></table></td></tr>"
    )


def note(text: str, tone: str = "amber") -> str:
    bg = {"amber": "#fffbf0", "green": "#eaf4ee", "red": "#fdf0f0"}[tone]
    bd = {"amber": "#f0e3bd", "green": "#cfe8d8", "red": "#f2c9c9"}[tone]
    fg = {"amber": "#6b5b1f", "green": "#1b7f4d", "red": "#a12d2d"}[tone]
    return (
        '<tr><td class="px" style="padding:16px 40px 8px 40px;">'
        f'<table class="card card-border" role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:{bg};border:1px solid {bd};border-radius:8px;">'
        '<tr><td style="padding:16px 20px;">'
        f'<p style="margin:0;font-size:13px;line-height:1.6;color:{fg};">{text}</p>'
        "</td></tr></table></td></tr>"
    )


def button(label: str, url: str, variant: str = "navy", note_line: str | None = None) -> str:
    if variant == "gold":
        bg, fg = "#c9a227", "#0f2a43"
    else:
        bg, fg = "#1e3a5f", "#ffffff"
    out = (
        '<tr><td class="px btn-cell" style="padding:24px 40px 8px 40px;text-align:center;">'
        f'<a class="btn" href="{url}" style="display:inline-block;padding:15px 34px;background-color:{bg};color:{fg};font-size:15px;font-weight:700;text-decoration:none;border-radius:6px;">{label}</a>'
        "</td></tr>"
    )
    if note_line:
        out += (
            '<tr><td class="px" style="padding:10px 40px 8px 40px;text-align:center;">'
            f'<p class="text-secondary" style="margin:0;font-size:12px;color:#5b6770;">{note_line}</p>'
            "</td></tr>"
        )
    return out


def para(text: str) -> str:
    return (
        '<tr><td class="px" style="padding:8px 40px 8px 40px;">'
        f'<p class="text-secondary" style="margin:0;font-size:14px;line-height:1.6;color:#5b6770;">{text}</p>'
        "</td></tr>"
    )


def table_heading(*cols: tuple[str, str]) -> str:
    cells = "".join(
        f'<td class="table-head" style="background-color:#1e3a5f;padding:10px 14px;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.6px;color:#ffffff;{align}">{label}</td>'
        for label, align in cols
    )
    return f'<tr>{cells}</tr>'


def build_html(*, subject: str, module: str, preheader: str, body: str) -> str:
    html = _SHELL
    html = html.replace("__SUBJECT__", subject)
    html = html.replace("__MODULE__", module)
    html = html.replace("__PREHEADER__", preheader)
    html = html.replace("__BODY__", body)
    return html


# ---------------------------------------------------------------------------
# Template catalog
# ---------------------------------------------------------------------------
T = []
def add(**kw) -> None:
    T.append(kw)


# ---- 1. User Account & Access --------------------------------------------
add(
    id="user_welcome_v1", module="User Account", version="v1",
    email_type="user.welcome", redirectable=False, tenant_overridable=True,
    description="New user onboarding — activation link. NEVER redirected.",
    subject="Welcome to {{tenant.name}} — Your Account Is Ready",
    preheader="Your {{tenant.name}} account is ready. Activate it in one click.",
    html=build_html(
        subject="Welcome to {{tenant.name}} — Your Account Is Ready", module="User Account",
        preheader="Your {{tenant.name}} account is ready. Activate it in one click.",
        body=hero("Welcome to {{tenant.name}}, {{userName}}",
                  "Your account has been created. You're one click away from managing sourcing, contracts, purchase orders, and invoices — all in one place.")
        + card("Your account", ("Full name", "{{userName}}"), ("Login email", "{{email}}"))
        + button("Activate Your Account", "{{activationLink}}", variant="gold",
                 note_line='Button not working? <a href="{{activationLink}}" style="color:#1e3a5f;">{{activationLink}}</a>')
        + para("If this account was not created by you, please contact your administrator."),
    ),
    text=(
        "Welcome to {{tenant.name}}, {{userName}}\n"
        "=====================================\n"
        "Your account has been created.\n"
        "  Full name:    {{userName}}\n"
        "  Login email:  {{email}}\n"
        "Activate your account: {{activationLink}}\n\n"
        "If this account was not created by you, please contact your administrator.\n\n"
        "{{tenant.footer}}\n{{tenant.disclaimer}}\n"
        "Language: {{i18n.en}} | {{i18n.fr}} | {{i18n.es}}\n"
    ),
    variables=["userName", "email", "activationLink", "year", "tenant.logo", "tenant.name", "tenant.footer", "tenant.disclaimer", "i18n.en", "i18n.fr", "i18n.es"],
)
add(
    id="user_password_reset_v1", module="User Account", version="v1",
    email_type="user.password_reset", redirectable=False, tenant_overridable=True,
    description="Password reset — security-critical. NEVER redirected.",
    subject="{{tenant.name}} Password Reset Request",
    preheader="We received a request to reset your {{tenant.name}} password.",
    html=build_html(
        subject="{{tenant.name}} Password Reset Request", module="User Account",
        preheader="We received a request to reset your {{tenant.name}} password.",
        body=hero("Password Reset Request",
                  "Hi {{userName}}, we received a request to reset the password for your {{tenant.name}} account. This link expires in {{expiresIn}}.")
        + button("Reset Your Password", "{{resetLink}}",
                 note_line='Button not working? <a href="{{resetLink}}" style="color:#1e3a5f;">{{resetLink}}</a>')
        + note("Security notice: if you did not request a password reset, you can safely ignore this email. "
               "Your password will not be changed unless you click the link above. Never share this link with anyone."),
    ),
    text=(
        "{{tenant.name}} Password Reset Request\n"
        "=====================================\n"
        "Hi {{userName}},\n"
        "Reset your password here (expires {{expiresIn}}): {{resetLink}}\n\n"
        "SECURITY NOTICE: If you did not request this, ignore this email. Your password "
        "will not change unless you click the link. Never share it.\n\n"
        "{{tenant.footer}}\n{{tenant.disclaimer}}\n"
    ),
    variables=["userName", "resetLink", "expiresIn", "year", "tenant.logo", "tenant.name", "tenant.footer", "tenant.disclaimer", "i18n.en", "i18n.fr", "i18n.es"],
)
add(
    id="user_account_locked_v1", module="User Account", version="v1",
    email_type="user.security", redirectable=True, tenant_overridable=True,
    description="Account lockout after repeated failed sign-in attempts.",
    subject="Security Alert: Your {{tenant.name}} Account Was Locked",
    preheader="Repeated sign-in attempts locked your account.",
    html=build_html(
        subject="Security Alert: Your {{tenant.name}} Account Was Locked", module="User Account",
        preheader="Repeated sign-in attempts locked your account.",
        body=hero("Your account was locked",
                  "Hi {{userName}}, your {{tenant.name}} account was locked after {{failedAttempts}} failed sign-in attempts.")
        + card("Lock details", ("Account", "{{email}}"), ("Locked at", "{{lockedAt}}"), ("Source IP", "{{sourceIp}}"))
        + button("Unlock My Account", "{{unlockLink}}")
        + note("If you did not attempt these sign-ins, please contact your administrator immediately — your account may be compromised.", tone="red"),
    ),
    text=(
        "Security Alert: Your {{tenant.name}} Account Was Locked\n"
        "Account: {{email}}\nLocked at: {{lockedAt}}\nFailed attempts: {{failedAttempts}}\n"
        "Unlock: {{unlockLink}}\n\n"
        "If you did not attempt these sign-ins, contact your administrator immediately.\n\n{{tenant.footer}}\n{{tenant.disclaimer}}\n"
    ),
    variables=["userName", "email", "failedAttempts", "lockedAt", "sourceIp", "unlockLink", "year", "tenant.logo", "tenant.name", "tenant.footer", "tenant.disclaimer", "i18n.en", "i18n.fr", "i18n.es"],
)

# ---- 2. Supplier Management ----------------------------------------------
add(
    id="supplier_registration_approved_v1", module="Supplier Management", version="v1",
    email_type="supplier.registration_approved", redirectable=True, tenant_overridable=True,
    description="Supplier registration approved — next steps to transact.",
    subject="{{tenant.name}} — Supplier Registration Approved",
    preheader="Your supplier registration with {{tenant.name}} has been approved.",
    html=build_html(
        subject="{{tenant.name}} — Supplier Registration Approved", module="Supplier Management",
        preheader="Your supplier registration with {{tenant.name}} has been approved.",
        body=hero("Your registration is approved",
                  "Dear {{companyName}}, thank you for registering with {{tenant.name}}. Your supplier registration has been approved and you can now transact.")
        + card("Registration", ("Supplier ID", "{{supplierId}}"), ("Company", "{{companyName}}"), ("Approved on", "{{approvedAt}}"), ("Tax ID", "{{taxId}}"))
        + button("Access the Supplier Portal", "{{portalUrl}}")
        + para("Your {{tenant.name}} buyer contact is {{buyerName}} ({{buyerEmail}})."),
    ),
    text=(
        "{{tenant.name}} — Supplier Registration Approved\n"
        "Dear {{companyName}},\nYour registration has been approved.\n"
        "  Supplier ID: {{supplierId}}\n  Approved on: {{approvedAt}}\n"
        "Access the portal: {{portalUrl}}\n\n"
        "Buyer contact: {{buyerName}} <{{buyerEmail}}>\n\n{{tenant.footer}}\n{{tenant.disclaimer}}\n"
    ),
    variables=["companyName", "supplierId", "approvedAt", "taxId", "portalUrl", "buyerName", "buyerEmail", "year", "tenant.logo", "tenant.name", "tenant.footer", "tenant.disclaimer", "i18n.en", "i18n.fr", "i18n.es"],
)
add(
    id="supplier_registration_rejected_v1", module="Supplier Management", version="v1",
    email_type="supplier.registration_rejected", redirectable=True, tenant_overridable=True,
    description="Supplier registration rejected with remediation guidance.",
    subject="{{tenant.name}} — Supplier Registration Update",
    preheader="An update is available for your supplier registration.",
    html=build_html(
        subject="{{tenant.name}} — Supplier Registration Update", module="Supplier Management",
        preheader="An update is available for your supplier registration.",
        body=hero("Update on your registration",
                  "Dear {{companyName}}, thank you for your interest in {{tenant.name}}. Your registration could not be approved at this time.")
        + card("Status", ("Supplier ID", "{{supplierId}}"), ("Status", "Rejected"), ("Reason", "{{rejectionReason}}"))
        + button("Review Feedback & Reapply", "{{portalUrl}}")
        + para("You may address the items above and reapply. Contact {{buyerName}} ({{buyerEmail}}) for questions."),
    ),
    text=(
        "{{tenant.name}} — Supplier Registration Update\n"
        "Dear {{companyName}},\nYour registration could not be approved.\n"
        "  Supplier ID: {{supplierId}}\n  Reason: {{rejectionReason}}\n"
        "Review and reapply: {{portalUrl}}\n\n{{tenant.footer}}\n{{tenant.disclaimer}}\n"
    ),
    variables=["companyName", "supplierId", "rejectionReason", "portalUrl", "buyerName", "buyerEmail", "year", "tenant.logo", "tenant.name", "tenant.footer", "tenant.disclaimer", "i18n.en", "i18n.fr", "i18n.es"],
)
add(
    id="supplier_requalification_v1", module="Supplier Management", version="v1",
    email_type="supplier.requalification", redirectable=True, tenant_overridable=True,
    description="Periodic supplier requalification request (certifications, financials).",
    subject="{{tenant.name}} — Supplier Requalification Required",
    preheader="Your supplier profile requires requalification.",
    html=build_html(
        subject="{{tenant.name}} — Supplier Requalification Required", module="Supplier Management",
        preheader="Your supplier profile requires requalification.",
        body=hero("Requalification required",
                  "Dear {{companyName}}, your {{tenant.name}} supplier profile requires requalification by {{dueDate}} to remain active.")
        + card("Requalification", ("Supplier ID", "{{supplierId}}"), ("Due date", "{{dueDate}}"), ("Required items", "{{requiredItems}}"))
        + button("Start Requalification", "{{portalUrl}}")
        + note("If you do not requalify by the due date, your profile may be placed on hold and future orders paused.", tone="amber"),
    ),
    text=(
        "{{tenant.name}} — Supplier Requalification Required\n"
        "Dear {{companyName}},\nRequalification is due by {{dueDate}}.\n"
        "  Supplier ID: {{supplierId}}\n  Required items: {{requiredItems}}\n"
        "Start now: {{portalUrl}}\n\nIf not completed by the due date, your profile may be placed on hold.\n\n{{tenant.footer}}\n{{tenant.disclaimer}}\n"
    ),
    variables=["companyName", "supplierId", "dueDate", "requiredItems", "portalUrl", "year", "tenant.logo", "tenant.name", "tenant.footer", "tenant.disclaimer", "i18n.en", "i18n.fr", "i18n.es"],
)
add(
    id="supplier_disqualification_v1", module="Supplier Management", version="v1",
    email_type="supplier.disqualification", redirectable=True, tenant_overridable=True,
    description="Supplier disqualification / suspension notice.",
    subject="{{tenant.name}} — Supplier Disqualification Notice",
    preheader="An important update on your supplier status.",
    html=build_html(
        subject="{{tenant.name}} — Supplier Disqualification Notice", module="Supplier Management",
        preheader="An important update on your supplier status.",
        body=hero("Disqualification notice",
                  "Dear {{companyName}}, this notice confirms the disqualification of your {{tenant.name}} supplier profile effective {{effectiveDate}}.")
        + card("Notice", ("Supplier ID", "{{supplierId}}"), ("Effective date", "{{effectiveDate}}"), ("Reason", "{{reason}}"), ("Reinstatement", "{{reinstatementPath}}"))
        + para("Outstanding purchase orders remain governed by their terms. Contact {{buyerName}} ({{buyerEmail}}) with any questions."),
    ),
    text=(
        "{{tenant.name}} — Supplier Disqualification Notice\n"
        "Dear {{companyName}},\nYour supplier profile has been disqualified effective {{effectiveDate}}.\n"
        "  Reason: {{reason}}\n  Reinstatement: {{reinstatementPath}}\n\n"
        "Outstanding purchase orders remain governed by their terms.\n\n{{tenant.footer}}\n{{tenant.disclaimer}}\n"
    ),
    variables=["companyName", "supplierId", "effectiveDate", "reason", "reinstatementPath", "buyerName", "buyerEmail", "year", "tenant.logo", "tenant.name", "tenant.footer", "tenant.disclaimer", "i18n.en", "i18n.fr", "i18n.es"],
)
add(
    id="supplier_performance_review_v1", module="Supplier Management", version="v1",
    email_type="supplier.performance", redirectable=True, tenant_overridable=True,
    description="Periodic supplier performance scorecard notification.",
    subject="{{tenant.name}} — Supplier Performance Review Available",
    preheader="Your quarterly performance scorecard is ready.",
    html=build_html(
        subject="{{tenant.name}} — Supplier Performance Review Available", module="Supplier Management",
        preheader="Your quarterly performance scorecard is ready.",
        body=hero("Performance scorecard available",
                  "Dear {{companyName}}, the {{period}} performance scorecard for your {{tenant.name}} account is now available.")
        + card("Scorecard", ("Supplier ID", "{{supplierId}}"), ("Overall score", "{{overallScore}}"), ("On-time delivery", "{{otdPercent}}"), ("Quality rating", "{{qualityRating}}"))
        + button("View Scorecard", "{{portalUrl}}")
        + para("Discuss improvements with your buyer {{buyerName}} ({{buyerEmail}}) before the next review cycle."),
    ),
    text=(
        "{{tenant.name}} — Supplier Performance Review Available\n"
        "Dear {{companyName}},\nYour {{period}} performance scorecard is available.\n"
        "  Overall score: {{overallScore}}\n  On-time delivery: {{otdPercent}}\n  Quality rating: {{qualityRating}}\n"
        "View: {{portalUrl}}\n\n{{tenant.footer}}\n{{tenant.disclaimer}}\n"
    ),
    variables=["companyName", "supplierId", "period", "overallScore", "otdPercent", "qualityRating", "portalUrl", "buyerName", "buyerEmail", "year", "tenant.logo", "tenant.name", "tenant.footer", "tenant.disclaimer", "i18n.en", "i18n.fr", "i18n.es"],
)

# ---- 3. Sourcing & RFx ---------------------------------------------------
add(
    id="rfq_invitation_v1", module="Sourcing & RFx", version="v1",
    email_type="rfx.invitation", redirectable=True, tenant_overridable=True,
    description="RFQ/RFP invitation to bid with event details and due date.",
    subject="{{tenant.name}} — RFQ Invitation: {{eventTitle}}",
    preheader="You are invited to respond to {{eventTitle}}.",
    html=build_html(
        subject="{{tenant.name}} — RFQ Invitation: {{eventTitle}}", module="Sourcing & RFx",
        preheader="You are invited to respond to {{eventTitle}}.",
        body=hero("Invitation to bid",
                  "Dear {{companyName}}, {{tenant.name}} invites you to respond to a sourcing event.")
        + card("Event", ("Event", "{{eventTitle}}"), ("Event ID", "{{eventId}}"), ("Type", "{{eventType}}"), ("Due date", "{{dueDate}}"), ("Currency", "{{currency}}"))
        + button("Respond to Event", "{{respondUrl}}")
        + para("Questions must be submitted by {{questionDeadline}}. Late responses will not be considered."),
    ),
    text=(
        "{{tenant.name}} — RFQ Invitation: {{eventTitle}}\n"
        "Dear {{companyName}},\nYou are invited to respond to a sourcing event.\n"
        "  Event: {{eventTitle}} ({{eventId}})\n  Type: {{eventType}}\n  Due: {{dueDate}}\n"
        "Respond here: {{respondUrl}}\nQuestions due by {{questionDeadline}}.\n\n{{tenant.footer}}\n{{tenant.disclaimer}}\n"
    ),
    variables=["companyName", "eventTitle", "eventId", "eventType", "dueDate", "currency", "respondUrl", "questionDeadline", "year", "tenant.logo", "tenant.name", "tenant.footer", "tenant.disclaimer", "i18n.en", "i18n.fr", "i18n.es"],
)
add(
    id="rfx_award_v1", module="Sourcing & RFx", version="v1",
    email_type="rfx.award", redirectable=True, tenant_overridable=True,
    description="Award notification after sourcing event close.",
    subject="{{tenant.name}} — Award Notification: {{eventTitle}}",
    preheader="The award decision for {{eventTitle}} is available.",
    html=build_html(
        subject="{{tenant.name}} — Award Notification: {{eventTitle}}", module="Sourcing & RFx",
        preheader="The award decision for {{eventTitle}} is available.",
        body=hero("Award decision",
                  "Dear {{companyName}}, the award decision for event {{eventTitle}} has been published.")
        + card("Award", ("Event", "{{eventTitle}}"), ("Event ID", "{{eventId}}"), ("Decision", "{{awardStatus}}"), ("Awarded value", "{{awardValue}}"))
        + button("View Award Details", "{{awardUrl}}")
        + para("If awarded, a purchase order will follow per the event terms. Thank you for participating."),
    ),
    text=(
        "{{tenant.name}} — Award Notification: {{eventTitle}}\n"
        "Dear {{companyName}},\nAward decision for {{eventTitle}} ({{eventId}}): {{awardStatus}}.\n"
        "  Awarded value: {{awardValue}}\nDetails: {{awardUrl}}\n\n{{tenant.footer}}\n{{tenant.disclaimer}}\n"
    ),
    variables=["companyName", "eventTitle", "eventId", "awardStatus", "awardValue", "awardUrl", "year", "tenant.logo", "tenant.name", "tenant.footer", "tenant.disclaimer", "i18n.en", "i18n.fr", "i18n.es"],
)

# ---- 4. Purchase Requisition (PR) ----------------------------------------
add(
    id="pr_approval_v1", module="PR", version="v1",
    email_type="pr.approval_required", redirectable=True, tenant_overridable=True,
    description="PR routed for approval — approver action required.",
    subject="{{tenant.name}} — PR {{prNumber}} Requires Your Approval",
    preheader="PR {{prNumber}} is awaiting your approval.",
    html=build_html(
        subject="{{tenant.name}} — PR {{prNumber}} Requires Your Approval", module="Purchase Requisition",
        preheader="PR {{prNumber}} is awaiting your approval.",
        body=hero("Approval required",
                  "Hi {{approverName}}, purchase requisition {{prNumber}} submitted by {{requesterName}} requires your approval.")
        + card("Requisition", ("PR number", "{{prNumber}}"), ("Requested by", "{{requesterName}}"), ("Description", "{{prDescription}}"), ("Amount", "{{prAmount}} {{currency}}"), ("Category", "{{category}}"), ("Due by", "{{dueDate}}"))
        + button("Approve", "{{approveUrl}}", variant="gold")
        + button("Review / Reject", "{{reviewUrl}}")
        + para("This approval is part of workflow '{{workflowName}}'. You have {{approvalSlaHours}} hours before escalation."),
    ),
    text=(
        "{{tenant.name}} — PR {{prNumber}} Requires Your Approval\n"
        "Hi {{approverName}},\nPR {{prNumber}} from {{requesterName}} requires your approval.\n"
        "  Amount: {{prAmount}} {{currency}}\n  Category: {{category}}\n  Due by: {{dueDate}}\n"
        "Approve: {{approveUrl}}\nReview/Reject: {{reviewUrl}}\n"
        "Workflow '{{workflowName}}' — escalation after {{approvalSlaHours}}h.\n\n{{tenant.footer}}\n{{tenant.disclaimer}}\n"
    ),
    variables=["approverName", "requesterName", "prNumber", "prDescription", "prAmount", "currency", "category", "dueDate", "approveUrl", "reviewUrl", "workflowName", "approvalSlaHours", "year", "tenant.logo", "tenant.name", "tenant.footer", "tenant.disclaimer", "i18n.en", "i18n.fr", "i18n.es"],
)
add(
    id="pr_rejected_v1", module="PR", version="v1",
    email_type="pr.rejected", redirectable=True, tenant_overridable=True,
    description="PR rejected back to requester with reason.",
    subject="{{tenant.name}} — PR {{prNumber}} Rejected",
    preheader="PR {{prNumber}} was rejected.",
    html=build_html(
        subject="{{tenant.name}} — PR {{prNumber}} Rejected", module="Purchase Requisition",
        preheader="PR {{prNumber}} was rejected.",
        body=hero("Requisition rejected",
                  "Hi {{requesterName}}, purchase requisition {{prNumber}} was rejected by {{approverName}}.")
        + card("Requisition", ("PR number", "{{prNumber}}"), ("Amount", "{{prAmount}} {{currency}}"), ("Rejected by", "{{approverName}}"), ("Reason", "{{rejectionReason}}"))
        + button("Revise & Resubmit", "{{resubmitUrl}}")
        + para("Please revise the requisition per the feedback and resubmit. Contact your buyer for guidance."),
    ),
    text=(
        "{{tenant.name}} — PR {{prNumber}} Rejected\n"
        "Hi {{requesterName}},\nPR {{prNumber}} was rejected by {{approverName}}.\n"
        "  Reason: {{rejectionReason}}\nRevise and resubmit: {{resubmitUrl}}\n\n{{tenant.footer}}\n{{tenant.disclaimer}}\n"
    ),
    variables=["requesterName", "approverName", "prNumber", "prAmount", "currency", "rejectionReason", "resubmitUrl", "year", "tenant.logo", "tenant.name", "tenant.footer", "tenant.disclaimer", "i18n.en", "i18n.fr", "i18n.es"],
)

# ---- 5. Purchase Order (PO) ----------------------------------------------
add(
    id="po_dispatch_v1", module="PO", version="v1",
    email_type="po.dispatch", redirectable=True, tenant_overridable=True,
    description="PO dispatched to supplier for acknowledgement.",
    subject="{{tenant.name}} — Purchase Order {{poNumber}} Dispatch",
    preheader="PO {{poNumber}} has been dispatched to you.",
    html=build_html(
        subject="{{tenant.name}} — Purchase Order {{poNumber}} Dispatch", module="Purchase Order",
        preheader="PO {{poNumber}} has been dispatched to you.",
        body=hero("New purchase order",
                  "Dear {{companyName}}, {{tenant.name}} has issued purchase order {{poNumber}}.")
        + card("Order", ("PO number", "{{poNumber}}"), ("PO date", "{{poDate}}"), ("Buyer", "{{buyerName}}"), ("Delivery date", "{{deliveryDate}}"), ("Order total", "{{poTotal}} {{currency}}"))
        + button("Acknowledge PO", "{{acknowledgeUrl}}")
        + para("Please acknowledge receipt by {{ackDeadline}}. Confirm ship-to {{shipToAddress}} and payment terms {{paymentTerms}}."),
    ),
    text=(
        "{{tenant.name}} — Purchase Order {{poNumber}} Dispatch\n"
        "Dear {{companyName}},\nPO {{poNumber}} dated {{poDate}} has been issued.\n"
        "  Total: {{poTotal}} {{currency}}\n  Delivery: {{deliveryDate}}\n  Ship to: {{shipToAddress}}\n"
        "Acknowledge by {{ackDeadline}}: {{acknowledgeUrl}}\n\n{{tenant.footer}}\n{{tenant.disclaimer}}\n"
    ),
    variables=["companyName", "poNumber", "poDate", "buyerName", "deliveryDate", "poTotal", "currency", "shipToAddress", "paymentTerms", "ackDeadline", "acknowledgeUrl", "year", "tenant.logo", "tenant.name", "tenant.footer", "tenant.disclaimer", "i18n.en", "i18n.fr", "i18n.es"],
)
add(
    id="po_change_v1", module="PO", version="v1",
    email_type="po.change", redirectable=True, tenant_overridable=True,
    description="Change order on an existing PO.",
    subject="{{tenant.name}} — PO {{poNumber}} Change Notice",
    preheader="A change has been made to PO {{poNumber}}.",
    html=build_html(
        subject="{{tenant.name}} — PO {{poNumber}} Change Notice", module="Purchase Order",
        preheader="A change has been made to PO {{poNumber}}.",
        body=hero("Purchase order change",
                  "Dear {{companyName}}, a change has been issued to purchase order {{poNumber}}.")
        + card("Change", ("PO number", "{{poNumber}}"), ("Change number", "{{changeNumber}}"), ("Change type", "{{changeType}}"), ("New total", "{{newTotal}} {{currency}}"))
        + button("Review Change", "{{reviewUrl}}")
        + para("Please review the updated terms and acknowledge the change by {{ackDeadline}}."),
    ),
    text=(
        "{{tenant.name}} — PO {{poNumber}} Change Notice\n"
        "Dear {{companyName}},\nChange {{changeNumber}} ({{changeType}}) issued to PO {{poNumber}}.\n"
        "  New total: {{newTotal}} {{currency}}\nReview: {{reviewUrl}}\nAcknowledge by {{ackDeadline}}.\n\n{{tenant.footer}}\n{{tenant.disclaimer}}\n"
    ),
    variables=["companyName", "poNumber", "changeNumber", "changeType", "newTotal", "currency", "reviewUrl", "ackDeadline", "year", "tenant.logo", "tenant.name", "tenant.footer", "tenant.disclaimer", "i18n.en", "i18n.fr", "i18n.es"],
)
add(
    id="order_confirmation_v1", module="PO", version="v1",
    email_type="order.confirmation", redirectable=False, tenant_overridable=True,
    description="Buyer-side order confirmation (PO placed). NEVER redirected (spec exception).",
    subject="{{tenant.name}} Order Confirmation — {{poNumber}}",
    preheader="Your order {{poNumber}} is confirmed.",
    html=build_html(
        subject="{{tenant.name}} Order Confirmation — {{poNumber}}", module="Purchase Order",
        preheader="Your order {{poNumber}} is confirmed.",
        body=hero("Thank you, {{userName}} — your order is confirmed",
                  "Your order {{poNumber}} has been placed and is being processed.")
        + card("Order", ("Order number", "{{poNumber}}"), ("Order date", "{{orderDate}}"), ("Order total", "{{orderTotal}} {{currency}}"))
        + button("Track Your Order", "{{trackingUrl}}")
        + para("You will receive shipping updates as your items move through fulfillment. Questions? Contact {{supportEmail}}."),
    ),
    text=(
        "{{tenant.name}} Order Confirmation — {{poNumber}}\n"
        "Thank you, {{userName}}. Your order {{poNumber}} is confirmed.\n"
        "  Total: {{orderTotal}} {{currency}}\n  Date: {{orderDate}}\n"
        "Track: {{trackingUrl}}\n\n{{tenant.footer}}\n{{tenant.disclaimer}}\n"
    ),
    variables=["userName", "poNumber", "orderDate", "orderTotal", "currency", "trackingUrl", "supportEmail", "year", "tenant.logo", "tenant.name", "tenant.footer", "tenant.disclaimer", "i18n.en", "i18n.fr", "i18n.es"],
)

# ---- 6. Receipts ---------------------------------------------------------
add(
    id="receipt_confirmation_v1", module="Receipts", version="v1",
    email_type="receipt.confirmation", redirectable=True, tenant_overridable=True,
    description="Goods receipt confirmation posted against a PO.",
    subject="{{tenant.name}} — Receipt Confirmation {{receiptNumber}}",
    preheader="Receipt {{receiptNumber}} has been posted.",
    html=build_html(
        subject="{{tenant.name}} — Receipt Confirmation {{receiptNumber}}", module="Receipts",
        preheader="Receipt {{receiptNumber}} has been posted.",
        body=hero("Goods receipt posted",
                  "Hi {{userName}}, receipt {{receiptNumber}} against purchase order {{poNumber}} has been posted.")
        + card("Receipt", ("Receipt number", "{{receiptNumber}}"), ("PO number", "{{poNumber}}"), ("Received on", "{{receiptDate}}"), ("Received by", "{{receivedBy}}"), ("Quantity", "{{receivedQty}} / {{orderedQty}}"))
        + button("View Receipt", "{{receiptUrl}}")
        + para("The receipt is now ready for invoice matching. Discrepancies are flagged automatically."),
    ),
    text=(
        "{{tenant.name}} — Receipt Confirmation {{receiptNumber}}\n"
        "Hi {{userName}},\nReceipt {{receiptNumber}} vs PO {{poNumber}} posted on {{receiptDate}}.\n"
        "  Quantity: {{receivedQty}} / {{orderedQty}}\nView: {{receiptUrl}}\n\n{{tenant.footer}}\n{{tenant.disclaimer}}\n"
    ),
    variables=["userName", "receiptNumber", "poNumber", "receiptDate", "receivedBy", "receivedQty", "orderedQty", "receiptUrl", "year", "tenant.logo", "tenant.name", "tenant.footer", "tenant.disclaimer", "i18n.en", "i18n.fr", "i18n.es"],
)
add(
    id="receipt_discrepancy_v1", module="Receipts", version="v1",
    email_type="receipt.discrepancy", redirectable=True, tenant_overridable=True,
    description="Quantity/price discrepancy flagged on a receipt.",
    subject="{{tenant.name}} — Receipt Discrepancy {{receiptNumber}}",
    preheader="A discrepancy was detected on receipt {{receiptNumber}}.",
    html=build_html(
        subject="{{tenant.name}} — Receipt Discrepancy {{receiptNumber}}", module="Receipts",
        preheader="A discrepancy was detected on receipt {{receiptNumber}}.",
        body=hero("Receipt discrepancy detected",
                  "Hi {{userName}}, a discrepancy was detected on receipt {{receiptNumber}} against PO {{poNumber}}.")
        + card("Discrepancy", ("Receipt number", "{{receiptNumber}}"), ("PO number", "{{poNumber}}"), ("Type", "{{discrepancyType}}"), ("Details", "{{discrepancyDetails}}"))
        + button("Resolve Discrepancy", "{{resolveUrl}}")
        + note("Resolve the discrepancy before the invoice can be matched for payment.", tone="amber"),
    ),
    text=(
        "{{tenant.name}} — Receipt Discrepancy {{receiptNumber}}\n"
        "Hi {{userName}},\nDiscrepancy ({{discrepancyType}}) on receipt {{receiptNumber}} vs PO {{poNumber}}.\n"
        "  Details: {{discrepancyDetails}}\nResolve: {{resolveUrl}}\n\n{{tenant.footer}}\n{{tenant.disclaimer}}\n"
    ),
    variables=["userName", "receiptNumber", "poNumber", "discrepancyType", "discrepancyDetails", "resolveUrl", "year", "tenant.logo", "tenant.name", "tenant.footer", "tenant.disclaimer", "i18n.en", "i18n.fr", "i18n.es"],
)

# ---- 7. Invoices & Invoice Verification ----------------------------------
add(
    id="invoice_exception_v1", module="Invoices", version="v1",
    email_type="invoice.exception", redirectable=True, tenant_overridable=True,
    description="Invoice blocked on exception during verification (2-way/3-way match).",
    subject="{{tenant.name}} — Invoice {{invoiceNumber}} Requires Attention",
    preheader="Invoice {{invoiceNumber}} is on exception.",
    html=build_html(
        subject="{{tenant.name}} — Invoice {{invoiceNumber}} Requires Attention", module="Invoices",
        preheader="Invoice {{invoiceNumber}} is on exception.",
        body=hero("Invoice exception",
                  "Hi {{userName}}, invoice {{invoiceNumber}} from {{supplierName}} requires attention before payment.")
        + card("Invoice", ("Invoice number", "{{invoiceNumber}}"), ("Supplier", "{{supplierName}}"), ("Invoice amount", "{{invoiceAmount}} {{currency}}"), ("Invoice date", "{{invoiceDate}}"))
        + card("Exception", ("Exception", "{{exceptionType}}"), ("Details", "{{exceptionDetails}}"), ("Match status", "{{matchStatus}}"))
        + button("Review Exception", "{{reviewUrl}}")
        + note("This invoice is blocked until the exception is resolved.", tone="amber"),
    ),
    text=(
        "{{tenant.name}} — Invoice {{invoiceNumber}} Requires Attention\n"
        "Hi {{userName}},\nInvoice {{invoiceNumber}} ({{supplierName}}) is on exception.\n"
        "  Amount: {{invoiceAmount}} {{currency}}\n  Exception: {{exceptionType}} — {{exceptionDetails}}\n  Match: {{matchStatus}}\n"
        "Review: {{reviewUrl}}\n\nThe invoice is blocked until resolved.\n\n{{tenant.footer}}\n{{tenant.disclaimer}}\n"
    ),
    variables=["userName", "supplierName", "invoiceNumber", "invoiceAmount", "currency", "invoiceDate", "exceptionType", "exceptionDetails", "matchStatus", "reviewUrl", "year", "tenant.logo", "tenant.name", "tenant.footer", "tenant.disclaimer", "i18n.en", "i18n.fr", "i18n.es"],
)
add(
    id="invoice_approved_v1", module="Invoices", version="v1",
    email_type="invoice.approved", redirectable=True, tenant_overridable=True,
    description="Invoice approved for payment.",
    subject="{{tenant.name}} — Invoice {{invoiceNumber}} Approved",
    preheader="Invoice {{invoiceNumber}} has been approved.",
    html=build_html(
        subject="{{tenant.name}} — Invoice {{invoiceNumber}} Approved", module="Invoices",
        preheader="Invoice {{invoiceNumber}} has been approved.",
        body=hero("Invoice approved",
                  "Hi {{userName}}, invoice {{invoiceNumber}} from {{supplierName}} has been approved for payment.")
        + card("Invoice", ("Invoice number", "{{invoiceNumber}}"), ("Supplier", "{{supplierName}}"), ("Approved amount", "{{approvedAmount}} {{currency}}"), ("Approved by", "{{approvedBy}}"))
        + para("The invoice will be scheduled for payment per the agreed terms. No further action is required."),
    ),
    text=(
        "{{tenant.name}} — Invoice {{invoiceNumber}} Approved\n"
        "Hi {{userName}},\nInvoice {{invoiceNumber}} approved for {{approvedAmount}} {{currency}}.\n"
        "  Approved by: {{approvedBy}}\nScheduled for payment per agreed terms.\n\n{{tenant.footer}}\n{{tenant.disclaimer}}\n"
    ),
    variables=["userName", "supplierName", "invoiceNumber", "approvedAmount", "currency", "approvedBy", "year", "tenant.logo", "tenant.name", "tenant.footer", "tenant.disclaimer", "i18n.en", "i18n.fr", "i18n.es"],
)

# ---- 8. Payments ---------------------------------------------------------
add(
    id="payment_completed_v1", module="Payments", version="v1",
    email_type="payment.completed", redirectable=True, tenant_overridable=True,
    description="Payment completed remittance advice.",
    subject="{{tenant.name}} — Payment Completed for Invoice {{invoiceNumber}}",
    preheader="Payment for invoice {{invoiceNumber}} has been completed.",
    html=build_html(
        subject="{{tenant.name}} — Payment Completed for Invoice {{invoiceNumber}}", module="Payments",
        preheader="Payment for invoice {{invoiceNumber}} has been completed.",
        body=hero("Payment completed",
                  "Dear {{companyName}}, payment for invoice {{invoiceNumber}} has been completed by {{tenant.name}}.")
        + card("Payment", ("Invoice number", "{{invoiceNumber}}"), ("Payment amount", "{{paymentAmount}} {{currency}}"), ("Payment date", "{{paymentDate}}"), ("Payment method", "{{paymentMethod}}"), ("Reference", "{{paymentReference}}"))
        + button("View Remittance", "{{remittanceUrl}}")
        + para("Please verify the remittance details against your records. Contact {{apContactEmail}} with any questions."),
    ),
    text=(
        "{{tenant.name}} — Payment Completed for Invoice {{invoiceNumber}}\n"
        "Dear {{companyName}},\nPayment completed.\n"
        "  Amount: {{paymentAmount}} {{currency}}\n  Date: {{paymentDate}}\n  Method: {{paymentMethod}}\n  Reference: {{paymentReference}}\n"
        "Remittance: {{remittanceUrl}}\n\n{{tenant.footer}}\n{{tenant.disclaimer}}\n"
    ),
    variables=["companyName", "invoiceNumber", "paymentAmount", "currency", "paymentDate", "paymentMethod", "paymentReference", "remittanceUrl", "apContactEmail", "year", "tenant.logo", "tenant.name", "tenant.footer", "tenant.disclaimer", "i18n.en", "i18n.fr", "i18n.es"],
)
add(
    id="payment_failed_v1", module="Payments", version="v1",
    email_type="payment.failed", redirectable=True, tenant_overridable=True,
    description="Payment execution failure notification.",
    subject="{{tenant.name}} — Payment Failed for Invoice {{invoiceNumber}}",
    preheader="A payment for invoice {{invoiceNumber}} could not be completed.",
    html=build_html(
        subject="{{tenant.name}} — Payment Failed for Invoice {{invoiceNumber}}", module="Payments",
        preheader="A payment for invoice {{invoiceNumber}} could not be completed.",
        body=hero("Payment failed",
                  "Hi {{userName}}, the payment for invoice {{invoiceNumber}} to {{supplierName}} could not be completed.")
        + card("Payment", ("Invoice number", "{{invoiceNumber}}"), ("Supplier", "{{supplierName}}"), ("Amount", "{{paymentAmount}} {{currency}}"), ("Reason", "{{failureReason}}"), ("Scheduled retry", "{{retryDate}}"))
        + button("Review Payment", "{{reviewUrl}}")
        + note("No funds left the account. Review the failure reason and correct the payment details.", tone="red"),
    ),
    text=(
        "{{tenant.name}} — Payment Failed for Invoice {{invoiceNumber}}\n"
        "Hi {{userName}},\nPayment to {{supplierName}} failed.\n"
        "  Amount: {{paymentAmount}} {{currency}}\n  Reason: {{failureReason}}\n  Retry: {{retryDate}}\n"
        "Review: {{reviewUrl}}\n\nNo funds left the account.\n\n{{tenant.footer}}\n{{tenant.disclaimer}}\n"
    ),
    variables=["userName", "supplierName", "invoiceNumber", "paymentAmount", "currency", "failureReason", "retryDate", "reviewUrl", "year", "tenant.logo", "tenant.name", "tenant.footer", "tenant.disclaimer", "i18n.en", "i18n.fr", "i18n.es"],
)

# ---- 9. System & Workflow Notifications ----------------------------------
add(
    id="workflow_action_required_v1", module="System & Workflow", version="v1",
    email_type="workflow.action_required", redirectable=True, tenant_overridable=True,
    description="Generic workflow task assigned — action required.",
    subject="{{tenant.name}} — Action Required: {{workflowTask}}",
    preheader="A workflow task has been assigned to you.",
    html=build_html(
        subject="{{tenant.name}} — Action Required: {{workflowTask}}", module="System & Workflow",
        preheader="A workflow task has been assigned to you.",
        body=hero("Action required",
                  "Hi {{userName}}, a workflow task '{{workflowTask}}' has been assigned to you on {{entityType}} {{entityNumber}}.")
        + card("Task", ("Task", "{{workflowTask}}"), ("Document", "{{entityType}} {{entityNumber}}"), ("Assigned by", "{{assignedBy}}"), ("Due by", "{{dueDate}}"))
        + button("Open Task", "{{taskUrl}}")
        + para("Unattended tasks are escalated after {{escalationHours}} hours. This is part of workflow '{{workflowName}}'."),
    ),
    text=(
        "{{tenant.name}} — Action Required: {{workflowTask}}\n"
        "Hi {{userName}},\nTask '{{workflowTask}}' assigned on {{entityType}} {{entityNumber}}.\n"
        "  Assigned by: {{assignedBy}}\n  Due by: {{dueDate}}\nOpen: {{taskUrl}}\n"
        "Escalation after {{escalationHours}}h.\n\n{{tenant.footer}}\n{{tenant.disclaimer}}\n"
    ),
    variables=["userName", "workflowTask", "entityType", "entityNumber", "assignedBy", "dueDate", "taskUrl", "workflowName", "escalationHours", "year", "tenant.logo", "tenant.name", "tenant.footer", "tenant.disclaimer", "i18n.en", "i18n.fr", "i18n.es"],
)
add(
    id="workflow_escalation_v1", module="System & Workflow", version="v1",
    email_type="workflow.escalation", redirectable=True, tenant_overridable=True,
    description="Workflow task escalated to a higher approver.",
    subject="{{tenant.name}} — Workflow Escalation: {{workflowTask}}",
    preheader="A workflow task has been escalated to you.",
    html=build_html(
        subject="{{tenant.name}} — Workflow Escalation: {{workflowTask}}", module="System & Workflow",
        preheader="A workflow task has been escalated to you.",
        body=hero("Task escalated",
                  "Hi {{userName}}, task '{{workflowTask}}' on {{entityType}} {{entityNumber}} has been escalated to you after exceeding its SLA.")
        + card("Escalation", ("Task", "{{workflowTask}}"), ("Document", "{{entityType}} {{entityNumber}}"), ("Original owner", "{{originalOwner}}"), ("Escalation reason", "{{escalationReason}}"), ("Due by", "{{dueDate}}"))
        + button("Take Action", "{{taskUrl}}")
        + note("This task exceeded the {{slaHours}} hour service-level target.", tone="amber"),
    ),
    text=(
        "{{tenant.name}} — Workflow Escalation: {{workflowTask}}\n"
        "Hi {{userName}},\nTask '{{workflowTask}}' on {{entityType}} {{entityNumber}} escalated to you.\n"
        "  Original owner: {{originalOwner}}\n  Reason: {{escalationReason}}\n  Due: {{dueDate}}\n"
        "Take action: {{taskUrl}}\n\n{{tenant.footer}}\n{{tenant.disclaimer}}\n"
    ),
    variables=["userName", "workflowTask", "entityType", "entityNumber", "originalOwner", "escalationReason", "dueDate", "taskUrl", "slaHours", "year", "tenant.logo", "tenant.name", "tenant.footer", "tenant.disclaimer", "i18n.en", "i18n.fr", "i18n.es"],
)
add(
    id="system_maintenance_v1", module="System & Workflow", version="v1",
    email_type="system.maintenance", redirectable=True, tenant_overridable=True,
    description="Scheduled platform maintenance notification.",
    subject="{{tenant.name}} — Scheduled Maintenance Notification",
    preheader="Scheduled maintenance for {{tenant.name}}.",
    html=build_html(
        subject="{{tenant.name}} — Scheduled Maintenance Notification", module="System & Workflow",
        preheader="Scheduled maintenance for {{tenant.name}}.",
        body=hero("Scheduled maintenance",
                  "Hi {{userName}}, {{tenant.name}} will undergo scheduled maintenance from {{startTime}} to {{endTime}} ({{timeZone}}).")
        + card("Maintenance", ("Start", "{{startTime}}"), ("End", "{{endTime}}"), ("Impact", "{{impact}}"), ("Status page", "{{statusUrl}}"))
        + para("Services will be unavailable during this window. Save your work and plan accordingly."),
    ),
    text=(
        "{{tenant.name}} — Scheduled Maintenance Notification\n"
        "Hi {{userName}},\nMaintenance window: {{startTime}} to {{endTime}} ({{timeZone}}).\n"
        "  Impact: {{impact}}\n  Status page: {{statusUrl}}\n\n{{tenant.footer}}\n{{tenant.disclaimer}}\n"
    ),
    variables=["userName", "startTime", "endTime", "timeZone", "impact", "statusUrl", "year", "tenant.logo", "tenant.name", "tenant.footer", "tenant.disclaimer", "i18n.en", "i18n.fr", "i18n.es"],
)

# ---------------------------------------------------------------------------
# Assemble catalog
# ---------------------------------------------------------------------------
def build_catalog() -> list[dict]:
    catalog = []
    for t in T:
        catalog.append(
            {
                "id": t["id"],
                "module": t["module"],
                "version": t["version"],
                "email_type": t["email_type"],
                "redirectable": t["redirectable"],
                "tenant_overridable": t["tenant_overridable"],
                "description": t["description"],
                "subject": t["subject"],
                "html": t["html"],
                "text": t["text"],
                "variables": sorted(set(t["variables"])),
            }
        )
    return catalog


def main() -> None:
    catalog = build_catalog()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(catalog, indent=2, ensure_ascii=False), encoding="utf-8")
    # Validate round-trip
    loaded = json.loads(OUTPUT.read_text(encoding="utf-8"))
    non_redir = [t["id"] for t in loaded if not t["redirectable"]]
    print(f"Wrote {len(loaded)} templates -> {OUTPUT}")
    print("Non-redirectable (spec exceptions):", ", ".join(non_redir))
    print("Modules covered:", ", ".join(sorted({t['module'] for t in loaded})))


if __name__ == "__main__":
    main()
