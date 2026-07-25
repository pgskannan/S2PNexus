"""Metadata Engine exception definitions."""

class MetadataNotFoundError(Exception):
    """Raised when a metadata entity cannot be found."""


class MetadataConflictError(Exception):
    """Raised when a metadata operation would violate uniqueness or integrity."""


class MetadataValidationError(Exception):
    """Raised when metadata input fails validation."""
