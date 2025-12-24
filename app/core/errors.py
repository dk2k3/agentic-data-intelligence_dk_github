class AgenticError(Exception):
    """Base class for all agentic errors."""


class PlanningError(AgenticError):
    """Failure during intent or query planning."""


class MetricResolutionError(AgenticError):
    """Metric could not be resolved from schema."""


class TimeResolutionError(AgenticError):
    """Time filter could not be resolved."""


class ExecutionError(AgenticError):
    """Pandas execution failed."""


class ValidationError(AgenticError):
    """Result shape or semantics invalid."""


class CorrectionError(AgenticError):
    """Self-correction failed to converge."""
