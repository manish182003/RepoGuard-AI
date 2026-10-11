from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_invalid_github_repository_url():
    response = client.get(
        "/github/repository",
        params={
            "url": "https://example.com/test"
        },
    )

    assert response.status_code == 400