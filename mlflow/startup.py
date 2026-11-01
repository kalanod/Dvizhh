import io
import os
import sys
from contextlib import redirect_stderr, redirect_stdout
from tempfile import NamedTemporaryFile

from sqlalchemy import URL


def main() -> None:
    authentication_enabled = "MLFLOW_AUTH_ADMIN_PASSWORD" in os.environ
    if authentication_enabled:
        if len(os.environ["MLFLOW_AUTH_ADMIN_PASSWORD"]) < 12:
            raise SystemExit("MLFLOW_AUTH_ADMIN_PASSWORD must contain at least 12 characters.")
        if not os.environ.get("MLFLOW_FLASK_SERVER_SECRET_KEY"):
            raise SystemExit("MLFLOW_FLASK_SERVER_SECRET_KEY is required for authentication.")

    try:
        password = os.environ["MLFLOW_DATABASE_PASSWORD"]
        if not password:
            raise ValueError("MLFLOW_DATABASE_PASSWORD is empty")
        database_uri = URL.create(
            "postgresql+psycopg2",
            username="mlflow",
            password=password,
            host="postgres",
            port=5432,
            database="mlflow",
        ).render_as_string(hide_password=False)
        os.environ["MLFLOW_BACKEND_STORE_URI"] = database_uri

        if authentication_enabled:
            with NamedTemporaryFile(
                mode="w", prefix="mlflow-auth-", suffix=".ini", encoding="utf-8", delete=False
            ) as config:
                config.write(
                    "[mlflow]\n"
                    "default_permission = NO_PERMISSIONS\n"
                    f"database_uri = {database_uri.replace('%', '%%')}\n"
                    "admin_username = admin\n"
                    "authorization_function = mlflow.server.auth:authenticate_request_basic_auth\n"
                )
                os.environ["MLFLOW_AUTH_CONFIG_PATH"] = config.name

        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            from mlflow.cli import cli

            cli.main(["db", "upgrade", database_uri], standalone_mode=False)
    except Exception as exc:
        print(f"Cannot prepare MLflow ({type(exc).__name__}).", file=sys.stderr)
        raise SystemExit(1) from None

    command = [
        "mlflow",
        "server",
        "--host",
        "0.0.0.0",
        "--port",
        "5000",
        "--artifacts-destination",
        "s3://mlflow-artifacts",
    ]
    if authentication_enabled:
        command.extend(["--app-name", "basic-auth"])
    os.execvp("mlflow", command)


if __name__ == "__main__":
    main()
