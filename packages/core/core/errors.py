class AgentHubError(Exception):
    """Base error for AgentHub runtime."""


class ProviderNotFoundError(AgentHubError):
    """Raised when a model provider name cannot be resolved from registry."""


class SkillNotFoundError(AgentHubError):
    """Raised when a skill name cannot be resolved from registry."""


class InvalidRunRequestError(AgentHubError):
    """Raised when a run request payload fails domain validation."""


class PlanningError(AgentHubError):
    """Raised when planning fails."""


class ExecutionError(AgentHubError):
    """Raised when execution fails."""
