from ..models import ExternalSource, Location, MediaAsset, Organization, Profile, Topic
from .base import BaseCRUDService


class ProfileService(BaseCRUDService[Profile]):
    model = Profile


class OrganizationService(BaseCRUDService[Organization]):
    model = Organization


class TopicService(BaseCRUDService[Topic]):
    model = Topic


class LocationService(BaseCRUDService[Location]):
    model = Location


class MediaAssetService(BaseCRUDService[MediaAsset]):
    model = MediaAsset


class ExternalSourceService(BaseCRUDService[ExternalSource]):
    model = ExternalSource
