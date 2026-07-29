"""Source-specific material collectors with one public dispatcher."""

from collectors.dispatch import collect
from collectors.models import CollectionDestination, CollectionRequest, CollectionResult

__all__ = ["collect", "CollectionDestination", "CollectionRequest", "CollectionResult"]
