"""Place lookup failures, independent of HTTP."""


class MapsUnavailableError(Exception):
    pass


class PlaceNotFoundError(Exception):
    pass


class InvalidPlaceQueryError(Exception):
    pass
