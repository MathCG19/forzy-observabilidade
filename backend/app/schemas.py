from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Severidade = Literal["normal", "alerta", "critico", "indeterminada"]


class SensorInfo(BaseModel):
    tag: str
    descricao: str
    unidade: str
    limite_alerta: float
    limite_critico: float


class LeituraAtual(BaseModel):
    tag: str
    descricao: str
    unidade: str
    valor: float | None
    timestamp_leitura: datetime
    severidade: Severidade
    qualidade: str | None
    limite_alerta: float
    limite_critico: float
    idade_s: float = Field(description="Segundos entre a leitura e o momento da resposta")
    desatualizado: bool = Field(description="Verdadeiro quando a idade passa do limite crítico de freshness")


class LeituraHistorico(BaseModel):
    timestamp_leitura: datetime
    valor: float | None
    severidade: Severidade
    qualidade: str | None


class Historico(BaseModel):
    tag: str
    unidade: str
    inicio: datetime
    fim: datetime
    quantidade: int
    leituras: list[LeituraHistorico]


class RegistroChamada(BaseModel):
    id: int
    timestamp_utc: str
    session_id: str
    feature: str
    metodo: str
    rota: str
    tag: str | None
    status_code: int
    latencia_ms: float
    headers_completos: bool
    idade_dado_s: float | None
    completude: float | None
    qtd_registros: int | None
    intervalo_medio_s: float | None
    intervalo_max_s: float | None
    severidade: str | None
    tamanho_resposta_bytes: int | None
    erro: str | None
    user_agent: str | None


class ListaRegistros(BaseModel):
    quantidade: int
    registros: list[RegistroChamada]


class Erro(BaseModel):
    detail: str
