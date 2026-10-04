from enum import StrEnum


class ProfileStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    DELETED = "DELETED"


class OrganizationRole(StrEnum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    EDITOR = "EDITOR"


class EventOrigin(StrEnum):
    USER = "USER"
    ORGANIZATION = "ORGANIZATION"
    EXTERNAL = "EXTERNAL"


class EventStatus(StrEnum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"
    ARCHIVED = "ARCHIVED"


class EventVisibility(StrEnum):
    PUBLIC = "PUBLIC"
    FRIENDS = "FRIENDS"
    UNLISTED = "UNLISTED"
    PRIVATE = "PRIVATE"


class EventJoinPolicy(StrEnum):
    OPEN = "OPEN"
    REQUEST = "REQUEST"
    INVITE_ONLY = "INVITE_ONLY"
    EXTERNAL = "EXTERNAL"


class EventFormat(StrEnum):
    OFFLINE = "OFFLINE"
    ONLINE = "ONLINE"
    HYBRID = "HYBRID"


class EventPriceType(StrEnum):
    FREE = "FREE"
    PAID = "PAID"


class EventManagerRole(StrEnum):
    OWNER = "OWNER"
    MANAGER = "MANAGER"


class OccurrenceStatus(StrEnum):
    SCHEDULED = "SCHEDULED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"


class ParticipationStatus(StrEnum):
    REQUESTED = "REQUESTED"
    GOING = "GOING"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class InvitationStatus(StrEnum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    DECLINED = "DECLINED"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


class FriendshipStatus(StrEnum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    DECLINED = "DECLINED"
    REMOVED = "REMOVED"


class MediaStatus(StrEnum):
    UPLOADING = "UPLOADING"
    READY = "READY"
    FAILED = "FAILED"
    DELETED = "DELETED"


class EventMediaRole(StrEnum):
    COVER = "COVER"
    GALLERY = "GALLERY"


class StoryStatus(StrEnum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"


class InteractionType(StrEnum):
    IMPRESSION = "IMPRESSION"
    OPEN = "OPEN"
    FAVORITE_ADD = "FAVORITE_ADD"
    FAVORITE_REMOVE = "FAVORITE_REMOVE"
    NOT_INTERESTED = "NOT_INTERESTED"
    JOIN_CLICK = "JOIN_CLICK"
    REQUEST_SUBMITTED = "REQUEST_SUBMITTED"
    REQUEST_ACCEPTED = "REQUEST_ACCEPTED"
    REQUEST_REJECTED = "REQUEST_REJECTED"
    PARTICIPATION_CANCELLED = "PARTICIPATION_CANCELLED"
    EXTERNAL_LINK_CLICK = "EXTERNAL_LINK_CLICK"
