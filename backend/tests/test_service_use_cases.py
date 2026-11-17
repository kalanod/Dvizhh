"""Service use cases work without FastAPI and keep validation before mutation."""

import asyncio
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest

from dvizh_backend.config import Settings
from dvizh_backend.database.services.exceptions import PermissionDeniedError
from dvizh_backend.services.maps_errors import InvalidPlaceQueryError, MapsUnavailableError
from dvizh_backend.services.maps_service import MapsService
from dvizh_backend.services.media_service import MediaService


def test_place_rules_fail_before_provider_calls():
    async def scenario():
        client = Mock()
        service = MapsService(Settings(_env_file=None), client)
        with pytest.raises(MapsUnavailableError):
            await service.suggest("place", "city", None, None, "https://example.test/")
        service.settings.yandex_maps_api_key = "unit-test-key"
        with pytest.raises(InvalidPlaceQueryError):
            await service.geocode("   ", "", "https://example.test/")
        client.fetch_json.assert_not_called()
    asyncio.run(scenario())


def test_place_service_preserves_canonical_company_snapshot():
    async def scenario():
        client = Mock()
        client.fetch_json.return_value = {"features": [{
            "geometry": {"coordinates": [139.65, 35.67]},
            "properties": {"CompanyMetaData": {"name": "Cafe", "address": "Tokyo"}},
        }]}
        service = MapsService(Settings(_env_file=None, yandex_maps_api_key="unit-test-key"), client)
        place = await service.geocode("ignored", "ymapsbm1://org?oid=one", "https://example.test/")
        assert place == {
            "name": "Cafe", "address_line": "Tokyo", "city": None,
            "longitude": "139.65", "latitude": "35.67",
        }
        args = client.fetch_json.call_args.args
        assert args[0] == "https://search-maps.yandex.ru/v1/"
        assert args[1]["uri"] == "ymapsbm1://org?oid=one"
    asyncio.run(scenario())


@pytest.mark.parametrize("remove", [False, True])
def test_avatar_assignment_coordinates_media_and_profile(remove):
    async def scenario():
        user_id, media_id = uuid4(), None if remove else uuid4()
        service = MediaService(Mock(), Mock(), Settings(_env_file=None))
        service.require_owned = AsyncMock()
        result = object()
        with patch("dvizh_backend.services.media_service.UserService") as factory:
            factory.return_value.update_profile = AsyncMock(return_value=result)
            assert await service.set_avatar(user_id, media_id) is result
            change = factory.return_value.update_profile.call_args.args[1]
            assert change.model_dump(exclude_unset=True) == {"avatar_media_id": media_id}
        if remove:
            service.require_owned.assert_not_awaited()
        else:
            service.require_owned.assert_awaited_once_with(media_id, user_id)
    asyncio.run(scenario())


def test_unowned_avatar_never_reaches_profile_mutation():
    async def scenario():
        service = MediaService(Mock(), Mock(), Settings(_env_file=None))
        service.require_owned = AsyncMock(side_effect=PermissionDeniedError("Not owned"))
        with patch("dvizh_backend.services.media_service.UserService") as factory:
            with pytest.raises(PermissionDeniedError):
                await service.set_avatar(uuid4(), uuid4())
            factory.assert_not_called()
    asyncio.run(scenario())
