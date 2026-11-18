class DatabaseDomainError(Exception):
    """Base error for domain-aware database operations."""


class EntityNotFoundError(DatabaseDomainError):
    pass


class InvalidStateTransitionError(DatabaseDomainError):
    pass


class InteractionConflictError(DatabaseDomainError):
    pass


class InteractionInputError(DatabaseDomainError):
    pass


class PermissionDeniedError(DatabaseDomainError):
    pass


class CapacityReachedError(DatabaseDomainError):
    pass


class JoinUnavailableError(DatabaseDomainError):
    pass


class InvalidTagSelectionError(Exception):
    pass


class EventSortError(Exception):
    """Ленту нельзя отсортировать выбранным способом (например, нет точки для «рядом»)."""
