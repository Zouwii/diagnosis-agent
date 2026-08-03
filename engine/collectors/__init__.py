"""Source-specific material collectors with one public dispatcher."""

from engine.collectors.dispatch import collect
from engine.collectors.models import CollectionDestination, CollectionRequest, CollectionResult

__all__ = ["collect", "CollectionDestination", "CollectionRequest", "CollectionResult"]
