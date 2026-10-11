import grpc
from grpc_health.v1 import health_pb2, health_pb2_grpc

from .config import get_settings
from .service import SERVICE_NAME


def main() -> None:
    host, port = get_settings().grpc_bind_address.rsplit(":", 1)
    host = {"0.0.0.0": "127.0.0.1", "[::]": "[::1]"}.get(host, host)
    try:
        with grpc.insecure_channel(f"{host}:{port}") as channel:
            response = health_pb2_grpc.HealthStub(channel).Check(
                health_pb2.HealthCheckRequest(service=SERVICE_NAME), timeout=2
            )
        healthy = response.status == health_pb2.HealthCheckResponse.SERVING
    except grpc.RpcError:
        healthy = False
    raise SystemExit(0 if healthy else 1)


if __name__ == "__main__":
    main()
