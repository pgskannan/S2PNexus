# S2PNexus — Enterprise Capability Matrix

Tracks the implementation status of every cross-cutting capability across every business domain.
Updated as of Sprint 2.5 — Platform Foundation freeze.

## Legend

- ✅ **Complete** — meets the Domain Development Standard for that capability
- 🔶 **Partial** — skeleton or prototype exists, not production-ready
- ⬜ **Not started** — not yet implemented

---

## Capability Matrix

| Capability         | Procurement | Supplier Lifecycle | Strategic Sourcing | Contract Lifecycle | Spend Intelligence |
|--------------------|:-----------:|:------------------:|:------------------:|:------------------:|:------------------:|
| Models             |      ✅     |        ✅          |        ✅          |        ✅          |        ✅          |
| Schemas            |      ✅     |        ✅          |        ✅          |        ✅          |        ✅          |
| CRUD/Repositories  |      ✅     |        ✅          |        ✅          |        ✅          |        ✅          |
| Workflow Services  |      ✅     |        ✅          |        🔶          |        ⬜          |        ⬜          |
| Commands           |      ✅     |        ✅          |        ✅          |        ⬜          |        ⬜          |
| Events             |      ✅     |        ✅          |        ⬜          |        ⬜          |        ⬜          |
| Audit              |      ✅     |        🔶          |        ⬜          |        ⬜          |        ⬜          |
| Notifications      |      ✅     |        🔶          |        ⬜          |        ⬜          |        ⬜          |
| AI Hooks / Agents  |      ✅     |        ✅          |        ✅          |        ✅          |        ✅          |
| RBAC               |      🔶     |        🔶          |        ⬜          |        ⬜          |        ⬜          |
| Tenant Isolation   |      ✅     |        ✅          |        ✅          |        ⬜          |        ⬜          |
| Integration Tests  |      ✅     |        ✅          |        ✅          |        🔶          |        ✅          |
| Unit Tests         |      ✅     |        ✅          |        ⬜          |        ⬜          |        ⬜          |

---

## Sprint Roadmap

```
v0.3.0
Platform Foundation         Sprint 1, 2A, 2.5
        │
        ▼
v0.4.0
Supplier Lifecycle          Sprint 3
        │
        ▼
v0.5.0
Strategic Sourcing          Sprint 4
        │
        ▼
v0.6.0
Contract Lifecycle          Sprint 5
        │
        ▼
v0.7.0
Spend Intelligence          Sprint 6
        │
        ▼
v0.8.0
AI Enablement               Sprint 7
        │
        ▼
v1.0.0
Enterprise S2PNexus
```

---

## Supplier Lifecycle — Full Scope (Sprint 3)

```text
Supplier Need
        │
Supplier Request     (implemented)
        │
Approval             (implemented)
        │
Invitation           (new)
        │
Registration         (implemented)
        │
Qualification        (new)
        │
Risk Assessment      (new)
        │
Compliance           (new)
        │
ERP Vendor Creation  (implemented via convert)
        │
Performance          (new)
        │
Continuous Monitoring (new)
```

---

## Definition of Complete (per domain)

A domain is considered **complete** when every capability row above shows ✅.
