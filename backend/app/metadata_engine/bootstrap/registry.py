"""Bootstrap registry and startup loader for metadata object registration."""

from __future__ import annotations

import importlib
import pkgutil
import secrets
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_password_hash
from app.metadata_engine.exceptions.metadata_errors import MetadataConflictError, MetadataValidationError
from app.metadata_engine.models import MetadataLayout, MetadataObject
from app.models.user import User, UserRole


BOOTSTRAP_PACKAGE = "app.metadata_engine.bootstrap"
_RESERVED_OBJECT_NAMES = {"metadata", "admin", "system", "tenant", "user"}
_SYSTEM_METADATA_USER_EMAIL = "metadata-bootstrap@localhost"


@dataclass(frozen=True)
class MetadataObjectDefinition:
    name: str
    display_name: str
    description: str | None
    entity_type: str
    searchable: bool = True
    auditable: bool = True
    supports_workflow: bool = False
    supports_approval: bool = False
    supports_attachments: bool = False
    supports_comments: bool = False
    supports_forms: bool = False
    classification: list[str] | None = None


@dataclass(frozen=True)
class MetadataLayoutDefinition:
    metadata_object_name: str
    version: int
    schema: dict
    security: dict | None = None
    ui_schema: dict | None = None
    locale: dict | None = None
    is_active: bool = True


_registered_metadata_objects: dict[str, MetadataObjectDefinition] = {}
_registered_metadata_layouts: dict[str, list[MetadataLayoutDefinition]] = {}


def _validate_metadata_object_definition(definition: MetadataObjectDefinition) -> None:
    if not definition.name or not definition.name.strip():
        raise MetadataValidationError("Metadata object name cannot be empty")
    if definition.name.lower() in _RESERVED_OBJECT_NAMES:
        raise MetadataValidationError(f"Metadata object name '{definition.name}' is reserved")
    if not definition.display_name or not definition.display_name.strip():
        raise MetadataValidationError("Metadata object display name cannot be empty")
    if not definition.entity_type or not definition.entity_type.strip():
        raise MetadataValidationError("Metadata object entity_type cannot be empty")
    lower_name = definition.name.lower()
    if lower_name in (name.lower() for name in _registered_metadata_objects):
        raise MetadataConflictError(f"Metadata object '{definition.name}' is already registered")


def _validate_metadata_layout_definition(definition: MetadataLayoutDefinition) -> None:
    if not definition.metadata_object_name or not definition.metadata_object_name.strip():
        raise MetadataValidationError("Metadata layout must reference a metadata object")
    if not isinstance(definition.schema, dict) or not definition.schema:
        raise MetadataValidationError("Metadata layout schema cannot be empty")
    if definition.version < 1:
        raise MetadataValidationError("Metadata layout version must be at least 1")


def register_metadata_object(definition: MetadataObjectDefinition) -> None:
    _validate_metadata_object_definition(definition)
    lower_name = definition.name.lower()
    _registered_metadata_objects[lower_name] = definition


def register_metadata_layout(definition: MetadataLayoutDefinition) -> None:
    _validate_metadata_layout_definition(definition)
    lower_object_name = definition.metadata_object_name.lower()
    if lower_object_name not in _registered_metadata_objects:
        raise MetadataValidationError(
            f"Metadata layout references unknown object '{definition.metadata_object_name}'"
        )
    _registered_metadata_layouts.setdefault(lower_object_name, []).append(definition)


def get_registered_metadata_objects() -> list[MetadataObjectDefinition]:
    return list(_registered_metadata_objects.values())


def get_registered_metadata_layouts() -> dict[str, list[MetadataLayoutDefinition]]:
    return {name: layouts[:] for name, layouts in _registered_metadata_layouts.items()}


def clear_metadata_registry() -> None:
    _registered_metadata_objects.clear()
    _registered_metadata_layouts.clear()


async def _ensure_system_user(db: AsyncSession) -> UUID:
    result = await db.execute(select(User).where(User.email == _SYSTEM_METADATA_USER_EMAIL))
    system_user = result.scalar_one_or_none()
    if system_user is None:
        system_user = User(
            email=_SYSTEM_METADATA_USER_EMAIL,
            full_name="Metadata Bootstrap",
            hashed_password=get_password_hash(secrets.token_urlsafe(32)),
            role=UserRole.ADMINISTRATOR,
            is_active=False,
            is_superuser=True,
        )
        db.add(system_user)
        await db.flush()
    return system_user.id


def _import_bootstrap_modules() -> None:
    package = importlib.import_module(BOOTSTRAP_PACKAGE)
    package_path = Path(package.__file__).parent
    for module_info in pkgutil.iter_modules([str(package_path)]):
        if module_info.ispkg:
            continue
        importlib.import_module(f"{BOOTSTRAP_PACKAGE}.{module_info.name}")


async def bootstrap_metadata_registry(
    db: AsyncSession,
    created_by: UUID | None = None,
    tenant_id: UUID | None = None,
) -> None:
    """Register metadata objects and layouts from bootstrap definitions."""
    _import_bootstrap_modules()

    created_by = created_by or await _ensure_system_user(db)

    for object_definition in get_registered_metadata_objects():
        existing_object = await db.execute(
            select(MetadataObject).where(func.lower(MetadataObject.name) == object_definition.name.lower())
        )
        metadata_object = existing_object.scalar_one_or_none()

        if metadata_object is None:
            metadata_object = MetadataObject(
                name=object_definition.name,
                display_name=object_definition.display_name,
                description=object_definition.description,
                entity_type=object_definition.entity_type,
                searchable=object_definition.searchable,
                auditable=object_definition.auditable,
                supports_workflow=object_definition.supports_workflow,
                supports_approval=object_definition.supports_approval,
                supports_attachments=object_definition.supports_attachments,
                supports_comments=object_definition.supports_comments,
                supports_forms=object_definition.supports_forms,
                classification=object_definition.classification,
                tenant_id=tenant_id,
                created_by=created_by,
            )
            db.add(metadata_object)
            await db.flush()

        layouts = get_registered_metadata_layouts().get(object_definition.name.lower(), [])
        for layout_definition in layouts:
            existing_layout = await db.execute(
                select(MetadataLayout)
                .where(MetadataLayout.metadata_object_id == metadata_object.id)
                .where(MetadataLayout.version == layout_definition.version)
            )
            if existing_layout.scalar_one_or_none() is not None:
                continue

            layout = MetadataLayout(
                metadata_object_id=metadata_object.id,
                version=layout_definition.version,
                schema=layout_definition.schema,
                security=layout_definition.security,
                ui_schema=layout_definition.ui_schema,
                locale=layout_definition.locale,
                is_active=layout_definition.is_active,
                created_by=created_by,
            )
            db.add(layout)

    await db.commit()


__all__ = [
    "MetadataObjectDefinition",
    "MetadataLayoutDefinition",
    "register_metadata_object",
    "register_metadata_layout",
    "get_registered_metadata_objects",
    "get_registered_metadata_layouts",
    "clear_metadata_registry",
    "bootstrap_metadata_registry",
]