from importlib.metadata import version

from fastapi.testclient import TestClient

from akshara import __version__


def test_root(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200

    body = response.json()
    assert body["name"] == "Akshara"
    assert body["name_native"] == "अक्षर"
    assert body["version"] == __version__ == version("akshara")
    assert body["features"]["ocr"] is True


def test_health(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "paddleocr": True}
