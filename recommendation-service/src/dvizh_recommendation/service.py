import grpc

from .generated import recommendation_service_pb2 as pb
from .generated import recommendation_service_pb2_grpc

SERVICE_NAME = pb.DESCRIPTOR.services_by_name["RecommendationService"].full_name


class RecommendationService(recommendation_service_pb2_grpc.RecommendationServiceServicer):
    async def GetRecommendations(
        self, request: pb.GetRecommendationsRequest, context: grpc.aio.ServicerContext
    ) -> pb.GetRecommendationsResponse:
        for field in ("user_id", "session_id", "request_id"):
            if not request.HasField(field) or not getattr(request, field).strip():
                await context.abort(grpc.StatusCode.INVALID_ARGUMENT, f"{field} is required")
        if request.HasField("page_token"):
            await context.abort(grpc.StatusCode.UNIMPLEMENTED, "Pagination is not implemented")
        return pb.GetRecommendationsResponse()
