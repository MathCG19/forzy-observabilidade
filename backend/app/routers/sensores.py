from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request

from app.providers.sensores import (
    CAMPOS_HISTORICO, CAMPOS_LEITURA, FonteIndisponivel, TagNaoEncontrada, completude,
)
from app.schemas import Erro, Historico, LeituraAtual, Limite, SensorInfo

router = APIRouter(prefix="/v1/sensores", tags=["sensores"])

RESPOSTAS_ERRO = {404: {"model": Erro}, 503: {"model": Erro}}
JANELA_MAXIMA = timedelta(days=7)


def _utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _falhar(request: Request, status: int, mensagem: str):
    request.state.obs = {**getattr(request.state, "obs", {}), "erro": mensagem}
    raise HTTPException(status_code=status, detail=mensagem)


@router.get("", response_model=list[SensorInfo], summary="Lista as tags disponíveis")
def listar_sensores(request: Request):
    return [
        SensorInfo(tag=s.tag, descricao=s.descricao, componente_id=s.componente_id,
                   limites={g: Limite(alerta=a, critico=c) for g, (a, c) in s.limites.items()})
        for s in request.app.state.provider.listar()
    ]


@router.get("/{tag}/leitura-atual", response_model=LeituraAtual, responses=RESPOSTAS_ERRO,
            summary="Leitura mais recente de um sensor")
def leitura_atual(tag: str, request: Request):
    provider = request.app.state.provider
    try:
        leitura = provider.leitura_atual(tag)
    except TagNaoEncontrada:
        _falhar(request, 404, f"Sensor '{tag}' não encontrado. Consulte GET /v1/sensores para ver as tags válidas.")
    except FonteIndisponivel as exc:
        _falhar(request, 503, f"Fonte de dados indisponível: {exc}")

    idade = (datetime.now(timezone.utc) - leitura["timestamp_leitura"]).total_seconds()
    request.state.obs = {
        "tag": leitura["tag"],
        "idade_dado_s": round(idade, 3),
        "completude": completude(leitura, CAMPOS_LEITURA),
        "severidade": leitura["severidade"],
    }
    return LeituraAtual(
        **leitura,
        idade_s=round(idade, 1),
        offline=idade > request.app.state.settings.limite_freshness_s,
    )


@router.get("/{tag}/historico", response_model=Historico, responses=RESPOSTAS_ERRO,
            summary="Leituras de um sensor num intervalo")
def historico(
    tag: str,
    request: Request,
    inicio: Annotated[datetime | None, Query(description="Início do intervalo (ISO 8601). Padrão: fim menos 1 hora")] = None,
    fim: Annotated[datetime | None, Query(description="Fim do intervalo (ISO 8601). Padrão: agora")] = None,
    limite: Annotated[int, Query(ge=1, le=5000, description="Máximo de leituras devolvidas")] = 120,
):
    fim = _utc(fim) if fim else datetime.now(timezone.utc)
    inicio = _utc(inicio) if inicio else fim - timedelta(hours=1)
    if inicio >= fim:
        _falhar(request, 422, "O parâmetro 'inicio' precisa ser anterior a 'fim'.")
    if fim - inicio > JANELA_MAXIMA:
        _falhar(request, 422, "O intervalo máximo de consulta é de 7 dias.")

    provider = request.app.state.provider
    try:
        leituras = provider.historico(tag, inicio, fim, limite)
    except TagNaoEncontrada:
        _falhar(request, 404, f"Sensor '{tag}' não encontrado. Consulte GET /v1/sensores para ver as tags válidas.")
    except FonteIndisponivel as exc:
        _falhar(request, 503, f"Fonte de dados indisponível: {exc}")

    tempos = [item["timestamp_leitura"].timestamp() for item in leituras]
    intervalos = [b - a for a, b in zip(tempos, tempos[1:])]
    request.state.obs = {
        "tag": tag.upper(),
        "qtd_registros": len(leituras),
        "completude": (sum(completude(item, CAMPOS_HISTORICO) for item in leituras) / len(leituras)) if leituras else None,
        "intervalo_medio_s": round(sum(intervalos) / len(intervalos), 2) if intervalos else None,
        "intervalo_max_s": max(intervalos) if intervalos else None,
    }
    return Historico(tag=provider.sensor(tag).tag, inicio=inicio, fim=fim,
                     quantidade=len(leituras), leituras=leituras)
