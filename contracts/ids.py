"""Typed identifiers. Kept as NewType aliases so logs stay readable strings."""

from typing import NewType

SessionId = NewType("SessionId", str)
CorrelationId = NewType("CorrelationId", str)
