from fastapi.testclient import TestClient
from app.main import app

client=TestClient(app)

def test_root():
    response=client.get("/")

    assert response.status_code==200
    assert response.json()=={
        "message": "Welcome to RepoGuard AI"
    }

def test_health():
    response=client.get("/health")

    assert response.status_code==200
    data=response.json()

    assert data["status"]=="ok"
    assert data["service"]=="RepoGuard AI"
    assert data["enviroment"]=="development"
