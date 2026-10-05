from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Query, Request

from app.observability.metrics import avaliar_conformidade, calcular_indicadores, carregar_contrato
from app.schemas import ListaRegistros

router = APIRouter(prefix="/v1/observabilidade", tags=["observabilidade"])


def _iso_utc(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    dt = dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    return dt.isoformat(timespec="milliseconds")


@router.get("", response_model=ListaRegistros, summary="Registros das chamadas às rotas de sensores")
def listar_registros(
    request: Request,
    feature: Annotated[str | None, Query(description="Filtra pelo valor do header X-Feature")] = None,
    session_id: Annotated[str | None, Query(description="Filtra pelo valor do header X-Session-Id")] = None,
    desde: Annotated[datetime | None, Query(description="Somente registros a partir deste instante (ISO 8601)")] = None,
    limite: Annotated[int, Query(ge=1, le=10000, description="Quantidade máxima, mais recentes primeiro no corte")] = 500,
):
    registros = request.app.state.store.listar(feature=feature, session_id=session_id,
                                               desde=_iso_utc(desde), limite=limite)
    return {"quantidade": len(registros), "registros": registros}


@router.get("/resumo", summary="Indicadores agregados e conformidade com o metric contract")
def resumo(
    request: Request,
    desde: Annotated[datetime | None, Query(description="Início da janela (ISO 8601)")] = None,
    ate: Annotated[datetime | None, Query(description="Fim da janela (ISO 8601)")] = None,
):
    registros = request.app.state.store.listar(desde=_iso_utc(desde), ate=_iso_utc(ate))
    indicadores = calcular_indicadores(registros)
    contrato = carregar_contrato(request.app.state.settings.contrato_path)
    conformidade = avaliar_conformidade(indicadores, contrato) if contrato else []
    return {"indicadores": indicadores, "conformidade": conformidade}
