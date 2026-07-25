# S2PNexus Domain Development Standard

Every new domain (and every refactored existing domain) **must** include all of the
layers below. This is the "definition of done" for domain implementation.

---

## Required Layers

```
backend/app/
  models/{domain}.py            # SQLAlchemy ORM models
  schemas/{domain}.py           # Pydantic request/response schemas
  crud/{domain}.py              # Database repository functions
  services/{domain}_workflow.py # Business/workflow logic
  commands/{domain}.py          # Command objects + handlers
  events/                       # Event types (event_type strings)
  routers/{domain}.py           # FastAPI endpoints

tests/
  unit/test_{domain}_*.py       # Unit tests per layer
  integration/test_{domain}_*.py # End-to-end API tests
```

---

## Required Cross-Cutting Integrations

Every domain **must** integrate these platform features:

| Feature | Integration Point |
|---------|------------------|
| **RBAC** | Every route uses `require_permission("domain:action")` |
| **Tenant Isolation** | Every CRUD function accepts `tenant_id` and filters queries |
| **Audit** | State transitions record via `ProcurementAuditEvent` or workflow history |
| **Notifications** | Workflow approval steps generate notifications |
| **Search** | List endpoints support `search=` with `ilike` filtering |
| **Pagination** | List endpoints use `skip`/`limit` Query params |
| **AI Hooks** | Agent tools registered in `app.agents.tools.register_default_tools` |

---

## Pattern: Command + Handler

Every state-changing operation must follow the command pattern:

```python
@dataclass(slots=True)
class MyActionCommand:
    aggregate_id: Any
    params: dict[str, Any] | None = None
    tenant_id: Any | None = None


class MyActionCommandHandler:
    def __init__(self, *, my_action_service: Callable[..., Awaitable[Any]]) -> None:
        self._service = my_action_service

    async def handle(self, command: MyActionCommand, *, db: Any, actor_id: Any) -> Any:
        return await self._service(db, command.aggregate_id,
            actor_id=actor_id, ..., tenant_id=command.tenant_id)
```

---

## Pattern: Event Publication

Every state transition publishes a `DomainEvent`:

```python
from app.events.publisher import EventPublisher

if event_bus is not None:
    publisher = EventPublisher(event_bus)
    await publisher.publish(
        event_type="MyDomainActioned",
        aggregate_type="my_domain",
        aggregate_id=str(entity.id),
        data=payload,
        actor=actor_id,
        tenant_id=tenant_id,
    )
```

---

## Pattern: Tenant-Aware CRUD

```python
async def get_my_entities(
    db: AsyncSession, skip=0, limit=100, search=None,
    status=None, tenant_id=None,
) -> list[MyEntity]:
    query = select(MyEntity)
    if status:
        query = query.where(MyEntity.status == status)
    if search:
        query = query.where(MyEntity.name.ilike(f"%{search}%"))
    if tenant_id is not None:
        query = query.where(MyEntity.tenant_id == tenant_id)
    query = query.order_by(desc(MyEntity.created_at)).offset(skip).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())
```

---

## Pattern: RBAC Router Endpoint

```python
from app.utils.dependencies import require_permission

@router.get("/items", ...)
async def list_items(
    current_user: Annotated[User, Depends(require_permission("domain:read"))],
    db: AsyncSession = Depends(get_db),
    ...
) -> ...:
    items = await get_items(db, ..., tenant_id=current_user.tenant_id)
```

---

## Validation Checklist for Code Review

- [ ] Model has `tenant_id`, `created_at`, `updated_at`
- [ ] Schema has `ConfigDict(from_attributes=True)` on responses
- [ ] CRUD accepts and filters on `tenant_id`
- [ ] At least one router endpoint uses `require_permission`
- [ ] State transitions have a command + handler (not called from router directly)
- [ ] State transitions publish a standardized `DomainEvent`
- [ ] List endpoints support `skip`, `limit`, `search`, `status`
- [ ] Tests cover: CRUD create/read/update/list, transition, tenant isolation, RBAC
