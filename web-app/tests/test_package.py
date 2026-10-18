import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dvizh_web import main


def test_package_import() -> None:
    import dvizh_web

    assert dvizh_web.__doc__


@pytest.fixture
def static_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text('<div id="root"></div>', encoding="utf-8")
    (static / "favicon.svg").write_text("<svg></svg>", encoding="utf-8")
    monkeypatch.setattr(main, "static_dir", static)
    return static


def test_spa_routes_return_index(static_dir: Path) -> None:
    client = TestClient(main.app)

    for path in ("/", "/events/42", "/profile"):
        response = client.get(path)
        assert response.status_code == 200
        assert 'id="root"' in response.text


def test_build_files_are_served(static_dir: Path) -> None:
    response = TestClient(main.app).get("/favicon.svg")

    assert response.status_code == 200
    assert response.text == "<svg></svg>"


def test_files_outside_build_are_not_served(static_dir: Path) -> None:
    (static_dir.parent / "secret.txt").write_text("secret", encoding="utf-8")

    response = asyncio.run(main.frontend("../secret.txt"))

    assert Path(response.path) == static_dir.resolve() / "index.html"


def test_missing_build_returns_503(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "static_dir", tmp_path)

    response = TestClient(main.app).get("/")

    assert response.status_code == 503
