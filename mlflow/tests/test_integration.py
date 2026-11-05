"""Verify authentication, model persistence and recovery on disposable volumes."""

import fcntl
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

PRODUCER = """
import json
import mlflow
import mlflow.sklearn
import pandas as pd
from mlflow.models import infer_signature
from sklearn.linear_model import LinearRegression

inputs = pd.DataFrame({"value": [0.0, 1.0, 2.0]})
versions = {}
for slope in (2, 3):
    targets = inputs["value"] * slope
    model = LinearRegression().fit(inputs, targets)
    with mlflow.start_run():
        mlflow.log_param("slope", slope)
        mlflow.log_metric("training_error", float(((model.predict(inputs) - targets) ** 2).mean()))
        mlflow.log_text("private artifact", "private.txt")
        artifact_uri = mlflow.get_artifact_uri("private.txt")
        saved = mlflow.sklearn.log_model(
            model, name="model", signature=infer_signature(inputs, model.predict(inputs)),
        )
        version = mlflow.register_model(saved.model_uri, "integration")
        versions[str(slope)] = version.version
print(json.dumps({"versions": versions, "artifact_uri": artifact_uri}))
"""

CONSUMER = """
import json
import sys
import mlflow
import pandas as pd
from mlflow import MlflowClient

client = MlflowClient()
for slope, number in json.loads(sys.argv[1]).items():
    version = client.get_model_version("integration", number)
    run = client.get_run(version.run_id)
    assert run.data.params["slope"] == slope
    assert run.data.metrics["training_error"] < 1e-10
    model = mlflow.pyfunc.load_model(f"models:/integration/{number}")
    assert model.metadata.signature is not None
    prediction = model.predict(pd.DataFrame({"value": [3.0]}))[0]
    assert abs(prediction - int(slope) * 3) < 1e-10, prediction
"""

ACCESS = """
import os
import sys
import requests

address = os.environ["MLFLOW_TRACKING_URI"]
certificate = os.environ["MLFLOW_TRACKING_SERVER_CERT_PATH"]
auth = (os.environ["MLFLOW_TRACKING_USERNAME"], os.environ["MLFLOW_TRACKING_PASSWORD"])
paths = ["/", "/api/2.0/mlflow/registered-models/search"]
if len(sys.argv) > 1:
    artifact_path = sys.argv[1].split(":/", 1)[1].lstrip("/")
    paths.append("/api/2.0/mlflow-artifacts/artifacts/" + artifact_path)
for path in paths:
    url = address + path
    for credentials in (None, (auth[0], "incorrect-password")):
        response = requests.get(url, auth=credentials, verify=certificate, timeout=10)
        assert response.status_code == 401, (path, response.status_code, response.text)
    response = requests.get(url, auth=auth, verify=certificate, timeout=10)
    assert response.status_code == 200, (path, response.status_code, response.text)
    if "mlflow-artifacts/artifacts/" in path:
        assert response.text == "private artifact", response.text
"""


PERMISSIONS = """
import os
import requests
from mlflow.server.auth.client import AuthServiceClient

address = os.environ["MLFLOW_TRACKING_URI"]
reader_password = os.environ["MLFLOW_TEST_READER_PASSWORD"]
client = AuthServiceClient(address)
client.create_user("reader", reader_password)
response = requests.get(
    address + "/api/2.0/mlflow/experiments/get", params={"experiment_id": "0"},
    auth=("reader", reader_password), verify=os.environ["MLFLOW_TRACKING_SERVER_CERT_PATH"],
    timeout=10,
)
assert response.status_code == 403, (response.status_code, response.text)
client.grant_user_permission("reader", "experiment", "0", "READ")
client.grant_user_permission("reader", "registered_model", "integration", "READ")
"""


class IntegrationTests(unittest.TestCase):
    def run_command(self, command: list[str], timeout: int = 120, check: bool = True) -> str:
        result = subprocess.run(
            command, env=self.environment, capture_output=True, text=True, timeout=timeout,
        )
        stdout, stderr = result.stdout, result.stderr
        for name, value in self.environment.items():
            if value and ("PASSWORD" in name or "SECRET" in name):
                stdout = stdout.replace(value, "<redacted>")
                stderr = stderr.replace(value, "<redacted>")
        if check and result.returncode:
            raise RuntimeError(stdout + stderr)
        return stdout.strip() if result.returncode == 0 else stdout + stderr

    def docker(self, *args: str, timeout: int = 120, check: bool = True) -> str:
        return self.run_command(["docker", *args], timeout=timeout, check=check)

    def source_sql(self, sql: str) -> str:
        return self.docker(
            *self.compose, "exec", "-T", "postgres", "psql", "-X",
            "--username", "source_test", "--dbname", "source_test", "--set", "ON_ERROR_STOP=1",
            "--tuples-only", "--no-align", "--command", sql,
        )

    def storage(self, command: str) -> str:
        return self.docker(
            *self.compose, "exec", "-T", "minio", "sh", "-ec",
            'mc alias set audit http://localhost:9000 "$MINIO_ROOT_USER" '
            '"$MINIO_ROOT_PASSWORD" >/dev/null\n' + command,
        )

    def test_production_registry_survives_recreation_and_backup_restore(self) -> None:
        repository = Path(__file__).resolve().parents[2]
        project = "dvizh-mlflow-test-" + uuid4().hex
        self.environment = {
            **os.environ,
            "COMPOSE_PROJECT_NAME": project,
            "POSTGRES_DB": "source_test",
            "POSTGRES_USER": "source_test",
            "POSTGRES_PASSWORD": "test-postgres-" + uuid4().hex,
            "RECSYS_READER_PASSWORD": "test-reader-" + uuid4().hex,
            "MINIO_ROOT_USER": "storage_test",
            "MINIO_ROOT_PASSWORD": "test-minio-" + uuid4().hex,
            "MLFLOW_DATABASE_PASSWORD": "test-mlflow-db-'@:/%$" + uuid4().hex,
            "MLFLOW_STORAGE_SECRET_KEY": "test-mlflow-storage-" + uuid4().hex,
            "MLFLOW_AUTH_ADMIN_PASSWORD": "test-mlflow-admin-" + uuid4().hex,
            "MLFLOW_FLASK_SERVER_SECRET_KEY": uuid4().hex + uuid4().hex,
            "MLFLOW_TRACKING_USERNAME": "admin",
            "MLFLOW_TEST_READER_PASSWORD": "test-reader-auth-" + uuid4().hex,
            "MLFLOW_DOMAIN": "mlflow.test",
        }
        self.environment["MLFLOW_TRACKING_PASSWORD"] = self.environment[
            "MLFLOW_AUTH_ADMIN_PASSWORD"
        ]
        with TemporaryDirectory(prefix=project) as temporary:
            directory = Path(temporary)
            environment_file = directory / "test.env"
            environment_file.touch()
            caddyfile = directory / "Caddyfile"
            caddyfile.write_text(
                "{$MLFLOW_DOMAIN} {\n  tls internal\n  reverse_proxy mlflow:5000\n}\n",
            )
            override = directory / "compose.test.yaml"
            override.write_text(
                "services:\n"
                "  mlflow:\n"
                "    environment:\n"
                "      MLFLOW_SERVER_ALLOWED_HOSTS: mlflow.test,mlflow:5000,localhost:*\n"
                "  mlflow-gateway:\n"
                "    ports: !override ['127.0.0.1::80', '127.0.0.1::443']\n"
                "    volumes:\n"
                f"      - {json.dumps(str(caddyfile) + ':/etc/caddy/Caddyfile:ro')}\n"
                "    networks:\n"
                "      default:\n"
                "        aliases: [mlflow.test]\n",
            )
            self.environment["COMPOSE_FILE"] = os.pathsep.join(
                str(path) for path in (
                    repository / "compose.yaml", repository / "compose.mlflow.prod.yaml", override,
                )
            )
            self.compose = (
                "compose", "--project-directory", str(repository),
                "--env-file", str(environment_file), "--profile", "ml",
            )
            try:
                self.docker(
                    *self.compose, "up", "--build", "--detach", "--wait",
                    "--wait-timeout", "120", "mlflow-gateway", timeout=600,
                )
                certificate = directory / "root.crt"
                self.docker(
                    *self.compose, "cp",
                    "mlflow-gateway:/data/caddy/pki/authorities/local/root.crt", str(certificate),
                )
                certificate.chmod(0o644)
                image = self.docker(*self.compose, "images", "--quiet", "mlflow")
                client = (
                    "run", "--rm", "--pull", "never", "--name", project + "-client",
                    "--network", project + "_default",
                    "--mount", f"type=bind,source={certificate},target=/tmp/root.crt,readonly",
                    "--env", "MLFLOW_TRACKING_URI=https://mlflow.test",
                    "--env", "MLFLOW_TRACKING_SERVER_CERT_PATH=/tmp/root.crt",
                    "--env", "MLFLOW_TRACKING_USERNAME", "--env", "MLFLOW_TRACKING_PASSWORD",
                    "--env", "MLFLOW_TEST_READER_PASSWORD",
                    "--entrypoint", "python", image, "-c",
                )
                self.docker(*client, ACCESS)
                saved = json.loads(self.docker(*client, PRODUCER).splitlines()[-1])
                versions = json.dumps(saved["versions"])
                self.assertEqual(len(set(saved["versions"].values())), 2)
                self.docker(*client, ACCESS, saved["artifact_uri"])
                self.docker(*client, PERMISSIONS)
                self.environment["MLFLOW_TRACKING_USERNAME"] = "reader"
                self.environment["MLFLOW_TRACKING_PASSWORD"] = self.environment[
                    "MLFLOW_TEST_READER_PASSWORD"
                ]
                self.docker(*client, CONSUMER, versions)
                self.docker(*self.compose, "run", "--rm", "--no-deps", "mlflow-init")
                self.docker(
                    *self.compose, "up", "--detach", "--no-deps", "--force-recreate", "--wait",
                    "--wait-timeout", "120", "mlflow",
                )
                self.docker(*client, CONSUMER, versions)
                self.source_sql(
                    "CREATE TABLE sentinel (value text); INSERT INTO sentinel VALUES ('kept');",
                )
                self.storage(
                    "mc mb audit/neighbour; printf kept | mc pipe audit/neighbour/sentinel",
                )
                backup = directory / "backup"
                backup_command = [
                    sys.executable, str(repository / "mlflow/backup.py"),
                    "--env-file", str(environment_file),
                ]
                with environment_file.open("rb") as lock:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    rejected = self.run_command(
                        [*backup_command, "backup", str(backup)], check=False,
                    )
                    self.assertIn("Another MLflow backup/restore is running.", rejected)
                    self.assertTrue(self.docker(
                        *self.compose, "ps", "--status", "running", "--quiet", "mlflow",
                    ))
                self.run_command([*backup_command, "backup", str(backup)], timeout=300)
                self.docker(*self.compose, "stop", "mlflow")
                self.source_sql("DROP DATABASE mlflow WITH (FORCE);")
                self.source_sql("CREATE DATABASE mlflow OWNER mlflow;")
                self.storage("mc rm --recursive --force audit/mlflow-artifacts")
                self.run_command([*backup_command, "restore", str(backup)], timeout=300)
                self.docker(
                    *self.compose, "up", "--detach", "--no-deps", "--wait",
                    "--wait-timeout", "120", "mlflow",
                )
                self.docker(*client, ACCESS, saved["artifact_uri"])
                self.docker(*client, CONSUMER, versions)
                self.assertEqual(self.source_sql("SELECT value FROM sentinel;"), "kept")
                self.assertEqual(self.storage("mc cat audit/neighbour/sentinel"), "kept")
            except Exception as error:
                logs = self.docker(
                    *self.compose, "logs", "--no-color", "mlflow", "mlflow-init", "mlflow-gateway",
                    check=False,
                )
                raise RuntimeError(f"{error}\n{logs}") from None
            finally:
                self.docker("rm", "--force", project + "-client", check=False)
                self.docker(
                    *self.compose, "down", "--volumes", "--remove-orphans", "--timeout", "10",
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
