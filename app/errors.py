"""Application exceptions."""


class ToolError(Exception):
    """Base class for tool failures."""


class ToolNotFoundError(ToolError):
    """Raised when a tool name is not in the registry."""


class ToolAlreadyRegisteredError(ToolError):
    """Raised when a tool name is registered twice."""


class ToolInputError(ToolError):
    """Raised when a tool payload fails validation."""


class SimulatedToolError(ToolError):
    """Controlled failure used by the failure simulator."""


class SimulatedTimeoutError(SimulatedToolError):
    """Deterministic timeout injected on the first web-search call."""


class SearchNetworkError(ToolError):
    """Retryable search failure: timeout, rate limit, or no usable results."""


class EmptySearchError(SearchNetworkError):
    """The provider returned no usable results. This is not a successful search."""


class SearchProviderError(ToolError):
    """Unexpected search-provider failure."""


class MalformedSearchError(ToolError):
    """Search provider returned a response that is not a result list."""


class CalculatorError(ToolError):
    """The expression is unsafe or cannot be evaluated."""


class StructuredOutputError(Exception):
    """The model response did not match the required schema."""


class LLMProviderError(Exception):
    """The model provider request failed."""


class PlanValidationError(Exception):
    """A generated plan failed structural validation."""


class PipelineError(Exception):
    """A research stage could not finish."""


class RecoveryExhausted(Exception):
    """A retryable operation failed after the retry budget was spent."""

    def __init__(self, original: BaseException, retry_count: int) -> None:
        super().__init__(f"{type(original).__name__}: {original}")
        self.original = original
        self.retry_count = retry_count
