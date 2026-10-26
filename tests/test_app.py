from fastapi.testclient import TestClient

from akshara.main import app

client = TestClient(app)


def test_root() -> None:
    response = client.get("/")

    assert response.status_code == 200

    body = response.json()
    assert body["name"] == "Akshara"
    assert body["name_native"] == "अक्षर"
    assert body["features"]["ocr"] is True


def test_health() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
