"""Application-level errors handled by the CLI boundary."""


class ApplicationError(Exception):
    """Expected application failure with a user-facing message."""

    def __init__(self, message: str, exit_code: int = 1) -> None:
        super().__init__(message)
        self.exit_code = exit_code


class CredentialsNotConfigured(ApplicationError):
    """Required Jira credentials are missing."""
