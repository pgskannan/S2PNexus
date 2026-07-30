"""
S2PNexus - Source-to-Pay Nexus Platform
Main FastAPI Application Entry Point
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import Counter, Histogram, generate_latest
from prometheus_client.openmetrics.exposition import CONTENT_TYPE_LATEST
from starlette.middleware.sessions import SessionMiddleware

from app.core.config import get_settings, Settings
from app.database.database import close_db, db_manager, init_db
from app.middleware.logging import LoggingMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.routers import health, auth, users, suppliers, contracts, documents, analytics, ai, procurement, sourcing, workflow, document_numbering, org_structure
from app.routers.commodity import router as commodity_router
from app.routers.gl_accounts import router as gl_accounts_router
from app.routers.categories import router as categories_router
from app.routers.address import router as address_router
from app.routers.budget import router as budget_router
from app.metadata_engine.bootstrap import bootstrap_metadata_registry
from app.metadata_engine.exceptions.metadata_errors import MetadataConflictError, MetadataNotFoundError, MetadataValidationError
from app.metadata_engine.router import router as metadata_router
from app.agents.startup import build_orchestrator
from app.events.event_bus import EventBus
from app.events.handlers.procurement import ProcurementEventHandler
from app.events.handlers.supplier import SupplierEventHandler

settings = get_settings()

# Prometheus metrics
REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager."""
    # Startup
    await init_db()
    app.state.orchestrator = build_orchestrator()
    app.state.event_bus = EventBus()
    procurement_handler = ProcurementEventHandler()
    app.state.event_bus.subscribe("PurchaseRequisitionSubmitted", procurement_handler)
    app.state.event_bus.subscribe("PurchaseRequisitionTransitioned", procurement_handler)
    app.state.procurement_event_handler = procurement_handler

    # NOTE: SupplierRequest/SupplierRegistration events were already being published
    # (see app.routers.suppliers -> apply_supplier_transition_workflow /
    # apply_supplier_registration_transition_workflow, both of which take an event_bus
    # kwarg and are called with app.state.event_bus), but nothing ever subscribed to
    # them -- every one of these fired into the void. Register a handler for all of them.
    supplier_handler = SupplierEventHandler()
    for supplier_event_type in (
        "SupplierRequestSubmitted",
        "SupplierRequestApproved",
        "SupplierRequestRejected",
        "SupplierRequestCancelled",
        "SupplierRegistrationSubmitted",
        "SupplierRegistrationUnderReview",
        "SupplierRegistrationApproved",
        "SupplierRegistrationRejected",
        "SupplierRegistrationCancelled",
    ):
        app.state.event_bus.subscribe(supplier_event_type, supplier_handler)
    app.state.supplier_event_handler = supplier_handler

    async with db_manager.session() as session:
        await bootstrap_metadata_registry(session)
        # Ensure a small starter set of categories exists for first-time deployments.
        try:
            from app.crud.category import count_categories, bulk_upsert_categories
            from app.models.document_numbering import NO_TENANT_ID

            existing = await count_categories(session, tenant_id=NO_TENANT_ID)
            if existing == 0:
                starter_categories = [
                    ("IT_HARDWARE", "IT Hardware"),
                    ("SOFTWARE", "Software"),
                    ("OFFICE_SUPPLIES", "Office Supplies"),
                    ("TRAVEL", "Travel"),
                    ("CONSULTING", "Consulting"),
                    ("MARKETING", "Marketing"),
                    ("HR", "HR"),
                    ("FACILITIES", "Facilities"),
                    ("EQUIPMENT", "Equipment"),
                    ("SERVICES", "Services"),
                    ("MRO", "MRO"),
                    ("INDIRECT", "Indirect Spend"),
                ]
                await bulk_upsert_categories(
                    session,
                    tenant_id=NO_TENANT_ID,
                    rows=[{"code": code, "name": name} for code, name in starter_categories],
                )
        except Exception:
            # Non-fatal: seeding should not prevent app startup. Any errors will
            # be visible in logs and can be retried via the admin upload endpoint.
            pass

        # Seed a default WorkflowDefinition per entity type so the approval
        # engine and its graph view actually have something to show out of the
        # box. Previously the only thing that created these rows was
        # backend/scripts/seed_workflow_definitions.py, a standalone script
        # nothing ever invoked in a deployed environment -- so
        # start_requisition_approval_workflow (services/procurement_workflow.py)
        # always found zero active definitions, returned None, and no
        # WorkflowInstance was ever created. Requisitions could still reach
        # approval_status="approved" via the legacy threshold check in the same
        # file, which made it look like "approval" happened with nothing for the
        # designer's graph view to actually display.
        try:
            from uuid import uuid4

            from sqlalchemy import select as _select

            from app.crud.workflow import create_workflow_definition, get_workflow_definitions
            from app.models.user import User, UserRole
            from app.schemas.workflow import WorkflowDefinitionCreate

            default_flows = [
                ("Requisition approval", "requisition", "Route requisition approvals through the workflow engine.", "Initial review"),
                ("Purchase order approval", "purchase_order", "Route PO approvals through the workflow engine.", "Finance review"),
                ("Goods receipt exception review", "goods_receipt", "Route goods receipt exceptions through the workflow engine.", "Exception review"),
                ("Invoice exception review", "invoice_exception", "Route invoice matching exceptions through the workflow engine.", "AP review"),
            ]

            # Default the single approval step's approver to the first admin
            # account so a seeded flow is actually completable, not just
            # visible. Best-effort: falls back to no approver (step stays
            # visible but requires an admin to add one via the designer) if no
            # administrator exists yet at first boot.
            admin_result = await session.execute(
                _select(User.id).where(User.role == UserRole.ADMINISTRATOR).limit(1)
            )
            default_approver = admin_result.scalar_one_or_none()
            default_approvers = [default_approver] if default_approver else []

            for name, entity_type, description, step_name in default_flows:
                existing = await get_workflow_definitions(session, entity_type=entity_type, is_active=True, limit=1)
                if existing:
                    continue
                payload = WorkflowDefinitionCreate(
                    name=name,
                    entity_type=entity_type,
                    description=description,
                    is_active=True,
                    steps=[
                        {
                            "name": step_name,
                            "step_type": "approval",
                            "approvers": default_approvers,
                            "required_approvals": 1,
                        }
                    ],
                )
                await create_workflow_definition(session, payload, created_by=default_approver or uuid4())
        except Exception:
            # Non-fatal: seeding should not prevent app startup.
            pass

    yield
    # Shutdown
    await close_db()


def create_app(settings_override: Settings | None = None) -> FastAPI:
    """Create and configure FastAPI application."""
    app_settings = settings_override or settings

    app = FastAPI(
        title=app_settings.APP_NAME,
        description=app_settings.APP_DESCRIPTION,
        version=app_settings.APP_VERSION,
        docs_url="/docs" if app_settings.is_development else None,
        redoc_url="/redoc" if app_settings.is_development else None,
        openapi_url="/openapi.json" if app_settings.is_development else None,
        lifespan=lifespan,
    )

    # Security middleware
    if not app_settings.is_development:
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=app_settings.ALLOWED_HOSTS,
        )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "X-Process-Time"],
    )

    # Compression middleware
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    # Session middleware
    app.add_middleware(
        SessionMiddleware,
        secret_key=app_settings.SECRET_KEY,
        max_age=app_settings.SESSION_MAX_AGE,
        https_only=app_settings.is_production,
    )

    # Custom middleware
    app.add_middleware(LoggingMiddleware)
    if app_settings.RATE_LIMIT_ENABLED:
        app.add_middleware(RateLimitMiddleware)

    # Prometheus metrics middleware
    @app.middleware("http")
    async def metrics_middleware(request: Request, call_next):
        import time

        start_time = time.time()
        response = await call_next(request)
        process_time = time.time() - start_time

        REQUEST_COUNT.labels(
            method=request.method,
            endpoint=request.url.path,
            status=response.status_code,
        ).inc()
        REQUEST_LATENCY.labels(
            method=request.method,
            endpoint=request.url.path,
        ).observe(process_time)

        response.headers["X-Process-Time"] = str(process_time)
        return response

    # Exception handlers
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        """Global exception handler."""
        import traceback
        import uuid

        request_id = str(uuid.uuid4())
        traceback.print_exc()

        if app_settings.is_development:
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Internal Server Error",
                    "message": str(exc),
                    "request_id": request_id,
                    "traceback": traceback.format_exc(),
                },
            )
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal Server Error",
                "message": "An unexpected error occurred",
                "request_id": request_id,
            },
        )

    # Health check endpoint (no auth required)
    @app.get("/health", tags=["Health"])
    async def health_check():
        """Health check endpoint."""
        db_healthy = await db_manager.health_check()
        return {
            "status": "healthy" if db_healthy else "degraded",
            "service": app_settings.APP_NAME,
            "version": app_settings.APP_VERSION,
            "database": "connected" if db_healthy else "disconnected",
        }

    # Prometheus metrics endpoint
    @app.get("/metrics", tags=["Monitoring"])
    async def metrics():
        """Prometheus metrics endpoint."""
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    # Include routers.
    # NOTE: auth/users/contracts/documents/analytics routers each declare their own
    # internal prefix (e.g. APIRouter(prefix="/contracts")), so they only need the
    # bare "/api/v1" here -- adding the segment again produces a doubled path like
    # "/api/v1/contracts/contracts". Routers that declare prefix="" (suppliers,
    # sourcing) or no prefix at all (health, ai) need the full segment supplied here.
    app.include_router(health.router, prefix="/api/v1", tags=["Health"])
    app.include_router(auth.router, prefix="/api/v1", tags=["Authentication"])
    app.include_router(users.router, prefix="/api/v1", tags=["Users"])
    app.include_router(suppliers.router, prefix="/api/v1/suppliers", tags=["Suppliers"])
    app.include_router(contracts.router, prefix="/api/v1", tags=["Contracts"])
    app.include_router(documents.router, prefix="/api/v1", tags=["Documents"])
    app.include_router(analytics.router, prefix="/api/v1", tags=["Analytics"])
    app.include_router(ai.router, prefix="/api/v1/ai", tags=["AI"])
    app.include_router(procurement.router, prefix="/api/v1", tags=["Procurement"])
    app.include_router(sourcing.router, prefix="/api/v1/sourcing", tags=["Sourcing"])
    app.include_router(workflow.router, prefix="/api/v1/workflow", tags=["Workflow"])
    app.include_router(document_numbering.router, prefix="/api/v1", tags=["Document Numbering"])
    app.include_router(commodity_router, prefix="/api/v1", tags=["Commodity Codes"])
    app.include_router(gl_accounts_router, prefix="/api/v1", tags=["GL Accounts"])
    app.include_router(categories_router, prefix="/api/v1", tags=["Categories"])
    app.include_router(address_router, prefix="/api/v1", tags=["Addresses"])
    app.include_router(budget_router, prefix="/api/v1", tags=["Budgets"])
    app.include_router(org_structure.router, prefix="/api/v1", tags=["OrgStructure"])
    app.include_router(metadata_router, prefix="/api/v1", tags=["Metadata"])

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.is_development,
        workers=1 if settings.is_development else settings.WORKERS,
        log_level=settings.LOG_LEVEL.lower(),
    )

    @app.exception_handler(MetadataNotFoundError)
    async def metadata_not_found_handler(request: Request, exc: MetadataNotFoundError):
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"error": "metadata_not_found", "message": str(exc)})

    @app.exception_handler(MetadataConflictError)
    async def metadata_conflict_handler(request: Request, exc: MetadataConflictError):
        return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"error": "metadata_conflict", "message": str(exc)})

    @app.exception_handler(MetadataValidationError)
    async def metadata_validation_handler(request: Request, exc: MetadataValidationError):
        return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content={"error": "metadata_validation", "message": str(exc)})