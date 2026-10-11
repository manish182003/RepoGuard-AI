import os
from fastapi import FastAPI
from fastapi.responses import FileResponse

from app.api.routes.health import router as health_router
from app.api.routes.github import router as github_router
from app.api.routes.investigation import router as investigation_router
from app.core.config import settings


from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(github_router)
app.include_router(investigation_router)


@app.get("/")
def root():
    return {
        "message": "Welcome to RepoGuard AI"
    }


from fastapi.staticfiles import StaticFiles

frontend_dist = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend", "dist"))
if os.path.exists(frontend_dist):
    assets_dir = os.path.join(frontend_dist, "assets")
    if os.path.exists(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/ui")
    @app.get("/app")
    def serve_react_app():
        return FileResponse(os.path.join(frontend_dist, "index.html"))


@app.get("/demo")
def live_demo():
    """Live Demonstration UI serving production React dashboard."""
    if os.path.exists(os.path.join(frontend_dist, "index.html")):
        return FileResponse(os.path.join(frontend_dist, "index.html"))
    static_html_path = os.path.join(os.path.dirname(__file__), "static", "demo.html")
    return FileResponse(static_html_path)
