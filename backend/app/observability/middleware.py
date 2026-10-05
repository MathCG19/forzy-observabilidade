import logging
import time
from datetime import datetime, timezone

from fastapi import FastAPI, Request

logger = logging.getLogger("observabilidade")

PREFIXO_OBSERVADO = "/v1/sensores"
AUSENTE = "ausente"


def agora_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _rota_template(request: Request) -> str:
    rota = request.scope.get("route")
    return getattr(rota, "path", request.url.path)


def montar_registro(request: Request, status_code: int, latencia_ms: float, tamanho: int | None,
                    erro: str | None = None) -> dict:
    session_id = request.headers.get("x-session-id")
    feature = request.headers.get("x-feature")
    # Dados de domínio que a rota calculou (idade do dado, completude etc.).
    extra = getattr(request.state, "obs", {})
    return {
        "timestamp_utc": agora_utc_iso(),
        "session_id": session_id or AUSENTE,
        "feature": feature or AUSENTE,
        "metodo": request.method,
        "rota": _rota_template(request),
        "tag": extra.get("tag") or request.path_params.get("tag"),
        "status_code": status_code,
        "latencia_ms": round(latencia_ms, 3),
        "headers_completos": bool(session_id and feature),
        "idade_dado_s": extra.get("idade_dado_s"),
        "completude": extra.get("completude"),
        "qtd_registros": extra.get("qtd_registros"),
        "intervalo_medio_s": extra.get("intervalo_medio_s"),
        "intervalo_max_s": extra.get("intervalo_max_s"),
        "severidade": extra.get("severidade"),
        "tamanho_resposta_bytes": tamanho,
        "erro": erro or extra.get("erro"),
        "user_agent": request.headers.get("user-agent"),
    }


def registrar_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def observabilidade(request: Request, call_next):
        if not request.url.path.startswith(PREFIXO_OBSERVADO):
            return await call_next(request)

        # Chamadas sem X-Session-Id ou X-Feature não são rejeitadas: ficam registradas
        # como "ausente" porque a cobertura de headers é um indicador do contrato.
        inicio = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception as exc:
            latencia = (time.perf_counter() - inicio) * 1000
            _gravar(request, montar_registro(request, 500, latencia, None, erro=repr(exc)))
            raise
        latencia = (time.perf_counter() - inicio) * 1000
        tamanho = response.headers.get("content-length")
        registro = montar_registro(request, response.status_code, latencia, int(tamanho) if tamanho else None)
        _gravar(request, registro)
        response.headers["X-Latencia-Ms"] = f"{latencia:.1f}"
        return response


def _gravar(request: Request, registro: dict) -> None:
    try:
        request.app.state.store.inserir(registro)
    except Exception:
        # A observabilidade nunca derruba a requisição observada.
        logger.exception("falha ao gravar registro de observabilidade")
