"""FastAPI application factory."""

from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from cps.api.middleware import CSRFMiddleware
from cps.api.routes import auth, dashboard, products, crawler, imports, audit


def create_app() -> FastAPI:
    from cps.config import get_settings
    settings = get_settings()

    app = FastAPI(
        title="CPS Admin API",
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
    )

    app.add_middleware(CSRFMiddleware)

    if settings.debug:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["http://localhost:5173"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    api_prefix = "/api/v1"
    app.include_router(auth.router, prefix=api_prefix)
    app.include_router(dashboard.router, prefix=api_prefix)
    app.include_router(products.router, prefix=api_prefix)
    app.include_router(crawler.router, prefix=api_prefix)
    app.include_router(imports.router, prefix=api_prefix)
    app.include_router(audit.router, prefix=api_prefix)

    @app.get(f"{api_prefix}/health")
    async def health():
        return {"status": "ok"}

    dist_path = Path(__file__).parent.parent.parent.parent / "web" / "dist"
    if dist_path.is_dir():
        from fastapi.staticfiles import StaticFiles
        app.mount("/", StaticFiles(directory=str(dist_path), html=True))

    return app
