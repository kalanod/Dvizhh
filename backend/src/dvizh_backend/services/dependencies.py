from dvizh_backend.database.dependencies import DatabaseSession

from .user_service import UserService


def get_user_service(session: DatabaseSession) -> UserService:
    return UserService(session)
