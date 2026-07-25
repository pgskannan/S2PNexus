# Metadata Engine

The Metadata Engine provides reusable platform metadata management capabilities.

## Responsibilities

- Define metadata fields that can be used across domain entities
- Store typed metadata values linked to entity types and IDs
- Support tenant isolation through tenant-aware field/value records
- Support RBAC through router dependencies and permission enforcement
- Publish domain events for metadata lifecycle actions

## Package structure

- `models/` - SQLAlchemy models for metadata fields and values
- `schemas/` - Pydantic schemas for API requests and responses
- `repository/` - Persistence abstractions for metadata operations
- `services/` - Business logic implementing validation and event dispatch
- `router/` - FastAPI endpoints for metadata field and value management
- `events/` - Domain event abstractions
- `exceptions/` - Domain-specific exception classes
- `expression_engine/` - Reusable expression parsing, validation, compilation, and runtime execution
- `tests/` - Unit tests

## Expression Engine

The Metadata Expression Engine supports:

- IF, AND, OR, NOT, CASE
- SUM, AVG, COUNT, MAX, MIN
- LOOKUP
- TODAY, NOW, DATEADD, DATEDIFF

It provides:

- parser for expression syntax
- validator for supported functions and dependency analysis
- cycle detection for expression trees
- compiler to an executable evaluator
- runtime execution with context values

## API

### Metadata fields and values
- `POST /api/v1/metadata/fields`
- `GET /api/v1/metadata/fields`
- `GET /api/v1/metadata/fields/{field_id}`
- `PATCH /api/v1/metadata/fields/{field_id}`
- `DELETE /api/v1/metadata/fields/{field_id}`
- `POST /api/v1/metadata/values`
- `GET /api/v1/metadata/values`
- `GET /api/v1/metadata/values/{value_id}`
- `PATCH /api/v1/metadata/values/{value_id}`
- `DELETE /api/v1/metadata/values/{value_id}`

### Metadata version management
- `POST /api/v1/metadata/versions/create`
- `POST /api/v1/metadata/versions/create/{object_id}`
- `POST /api/v1/metadata/versions/publish/{object_id}`
- `POST /api/v1/metadata/versions/rollback/{object_id}`
- `POST /api/v1/metadata/versions/restore/{object_id}`
- `GET /api/v1/metadata/versions`
- `GET /api/v1/metadata/versions/history`
- `GET /api/v1/metadata/versions/diff`

## Versioning behavior

- Version creation derives the next version from the latest layout for a metadata object.
- Publishing marks a version as active for the object.
- Rollback and restore create new version entries that preserve the selected version payload and can be diffed later.
- Comparison uses a simple schema/security/UI/locale diff payload for inspection and downstream automation.

## Dependency graph and impact analysis

The metadata engine now provides a lightweight dependency graph for metadata objects.

### Supported operations
- Dependency discovery across a directed dependency chain
- Circular dependency detection
- Impact analysis for downstream nodes
- Safe-delete validation for dependency-bearing nodes

### REST endpoints
- `POST /api/v1/metadata/dependencies/graph`
- `POST /api/v1/metadata/dependencies/dependents`
- `POST /api/v1/metadata/dependencies/impact`
- `POST /api/v1/metadata/dependencies/validate`

## Test suite

The metadata engine now includes enterprise-focused regression coverage for:
- repository and service behavior
- cache operations and cache-key semantics
- expression evaluation, validation, and dependency analysis
- bootstrap registry idempotency and system-user provisioning
- rollback/restore versioning flows
- dependency-graph traversal and impact analysis
- API access control, tenant isolation, and security validation

Run the suite with:
- `pytest backend/app/metadata_engine/tests -q`
- `pytest backend/app/metadata_engine/tests --cov=app.metadata_engine --cov-report=term-missing`

## Notes

- No Supplier-specific logic is present.
- Uses tenant-aware data separation via `tenant_id` fields.
- Uses dependency injection through `MetadataService` and `MetadataRepository`.
