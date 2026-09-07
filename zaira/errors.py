"""Application-level errors handled by the CLI boundary."""


class ApplicationError(Exception):
    """Expected application failure with a user-facing message."""

    def __init__(self, message: str, exit_code: int = 1) -> None:
        super().__init__(message)
        self.exit_code = exit_code


class CredentialsNotConfigured(ApplicationError):
    """Required Jira credentials are missing."""


class ResourceFetchFailed(Exception):
    """A remote fetch failed due to a transport/API error.

    Distinct from a resource legitimately having no data. Internal-only:
    raised by fetch helpers and caught by boundary adapters close to the
    call site so existing CLI output stays unchanged for now. Whether (and
    how) that boundary should instead report the failure is a separate
    compatibility decision -- see refactoring_plan.md.
    """
