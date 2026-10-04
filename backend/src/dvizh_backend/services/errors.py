class UserServiceError(Exception):
    """Expected user domain error, independent of HTTP and database drivers."""


class UserNotFoundError(UserServiceError):
    pass


class ProfileAlreadyExistsError(UserServiceError):
    pass


class UserInactiveError(UserServiceError):
    pass


class UsernameTakenError(UserServiceError):
    pass


class AvatarUnavailableError(UserServiceError):
    pass


class FriendshipStateError(UserServiceError):
    pass
