from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException

from dvizh_backend.api.dependencies import DatabaseSession
from dvizh_backend.api.schemas.interaction import InteractionBatchDTO, InteractionBatchResponseDTO
from dvizh_backend.api.security import AccountWriteActor
from dvizh_backend.database.services.interactions import InteractionService

router = APIRouter(prefix="/api/interactions", tags=["interactions"])


@router.post("", summary="Сохранить действия с мероприятиями.")
async def record_interactions(
    body: InteractionBatchDTO,
    user_id: AccountWriteActor,
    session: DatabaseSession,
    expected_account: Annotated[UUID | None, Header(alias="X-Dvizh-Account-Id")] = None,
) -> InteractionBatchResponseDTO:
    if expected_account is not None and expected_account != user_id:
        raise HTTPException(403, "Interaction batch belongs to another account")
    accepted = await InteractionService(session).record_batch(user_id, body.interactions)
    return InteractionBatchResponseDTO(accepted_interaction_ids=accepted)
