import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

import grpc_tools

ROOT = Path(__file__).resolve().parent
PACKAGE = Path("dvizh_recommendation/generated")


def generate(output: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "grpc_tools.protoc",
            f"-I{PACKAGE}={ROOT}",
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
    if not args.check:
        generate(ROOT / "src")
        return
    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory)
        generate(output)
        for generated in (output / PACKAGE).glob("*.py"):
            expected = ROOT / "src" / PACKAGE / generated.name
            if not expected.exists() or expected.read_bytes() != generated.read_bytes():
                raise SystemExit("Generated code is outdated; run uv run python generate_proto.py")


if __name__ == "__main__":
    main()
