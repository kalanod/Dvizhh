class DatabaseDomainError(Exception):
    """Base error for domain-aware database operations."""


class EntityNotFoundError(DatabaseDomainError):
    pass


class InvalidStateTransitionError(DatabaseDomainError):
    pass


class PermissionDeniedError(DatabaseDomainError):
    pass


class CapacityReachedError(DatabaseDomainError):
    pass


class JoinUnavailableError(DatabaseDomainError):
    pass
