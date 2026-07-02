"""
Compatibility layer for agent reasoning schemas.

DO NOT define new intent types or plans here.
All canonical schemas live in:
    app.schemas.final_reasoning_schema
"""

from app.schemas.final_reasoning_schema import (
    IntentType,
    TimePlan,
    FinalReasoningSchema,
)

__all__ = [
    "IntentType",
    "TimePlan",
    "FinalReasoningSchema",
]
