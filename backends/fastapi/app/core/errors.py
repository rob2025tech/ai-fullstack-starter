class BackendError(Exception):
    """Base for typed errors mapped to the contract error envelope."""

    code = "internal_error"
    http_status = 500

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class InvalidRequestError(BackendError):
    code = "invalid_request"
    http_status = 422


class ProviderError(BackendError):
    code = "provider_error"
    http_status = 502


class ProviderUnavailableError(BackendError):
    code = "provider_unavailable"
    http_status = 503


class UnauthorizedError(BackendError):
    code = "unauthorized"
    http_status = 401
