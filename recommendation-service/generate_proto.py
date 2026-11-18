import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

import grpc_tools

ROOT = Path(__file__).resolve().parent
PACKAGE = Path("dvizh_recommendation/generated")
BACKEND_OUTPUT = ROOT.parent / "backend" / "src" / "dvizh_backend" / "generated"


def generate(output: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "grpc_tools.protoc",
            f"-I{PACKAGE.as_posix()}={ROOT}",
            f"-I{Path(grpc_tools.__file__).parent / '_proto'}",
            f"--python_out={output}",
            f"--grpc_python_out={output}",
            str(ROOT / "recommendation_service.proto"),
        ],
        check=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory)
        generate(output)
        for generated in (output / PACKAGE).glob("*.py"):
            source = generated.read_text(encoding="utf-8")
            # Keep the protobuf descriptor identical in both packages.
            backend_source = source.replace(
                "from dvizh_recommendation.generated import recommendation_service_pb2",
                "from . import recommendation_service_pb2",
            ).replace(
                "'dvizh_recommendation.generated.recommendation_service_pb2'",
                "'dvizh_backend.generated.recommendation_service_pb2'",
            )
            for target, code in (
                (ROOT / "src" / PACKAGE / generated.name, source),
                (BACKEND_OUTPUT / generated.name, backend_source),
            ):
                if args.check:
                    if not target.exists() or target.read_text(encoding="utf-8") != code:
                        raise SystemExit(
                            f"{target.name} is outdated; run uv run python generate_proto.py"
                        )
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(code, encoding="utf-8")


if __name__ == "__main__":
    main()
