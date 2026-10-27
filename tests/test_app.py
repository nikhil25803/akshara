from fastapi.testclient import TestClient


def test_root(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200

    body = response.json()
    assert body["name"] == "Akshara"
    assert body["name_native"] == "अक्षर"
    assert body["features"]["ocr"] is True


def test_health(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "paddleocr": True}
