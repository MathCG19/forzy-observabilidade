import logging

from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError

from app.config import Settings
from app.observability.middleware import registrar_middleware
from app.observability.store import ObservabilidadeStore
from app.providers.sensores import SensoresProvider
from app.routers import observabilidade, sensores

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(
        title="Sensor Monitoring API",
        description="Provider de Sensores do Forzy Digital Twin com registro de observabilidade por chamada.",
        version="1.0.0",
    )
    app.state.settings = settings
    app.state.store = ObservabilidadeStore(settings.db_path)
    app.state.provider = SensoresProvider(
        simular_latencia=settings.simular_latencia,
        prob_falha=settings.prob_falha_fonte,
    )

    @app.exception_handler(RequestValidationError)
    async def validacao(request: Request, exc: RequestValidationError):
        # Guarda o motivo do 422 para que o registro de observabilidade saiba o que houve.
        campos = ", ".join(".".join(str(p) for p in e["loc"]) for e in exc.errors())
        request.state.obs = {"erro": f"parâmetros inválidos: {campos}"}
        return await request_validation_exception_handler(request, exc)

    app.include_router(sensores.router)
    app.include_router(observabilidade.router)
    registrar_middleware(app)

    @app.get("/", include_in_schema=False)
    def raiz():
        return {"servico": "Sensor Monitoring API", "documentacao": "/docs"}

    return app


app = create_app()
