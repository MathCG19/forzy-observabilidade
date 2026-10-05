from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Severidade = Literal["normal", "alerta", "critico", "indeterminada"]


class Limite(BaseModel):
    alerta: float
    critico: float


class SensorInfo(BaseModel):
    tag: str
    descricao: str
    componente_id: int
    limites: dict[str, Limite] = Field(description="Limiares por grandeza (Metric Contract do CS3)")


class SeveridadePorGrandeza(BaseModel):
    velocidade_mm_s: Literal["normal", "alerta", "critico"] | None
    aceleracao_g: Literal["normal", "alerta", "critico"] | None
    temperatura_c: Literal["normal", "alerta", "critico"] | None


class LeituraHistorico(BaseModel):
    timestamp_leitura: datetime
    velocidade_mm_s: float | None = Field(description="Velocidade de vibração RMS")
    aceleracao_g: float | None
    temperatura_c: float | None
    motor_ligado: bool | None = Field(description="Falso quando a vibração está abaixo de 0,3 mm/s")
    severidade: Severidade
    severidade_por_grandeza: SeveridadePorGrandeza


class LeituraAtual(LeituraHistorico):
    tag: str
    descricao: str
    componente_id: int
    idade_s: float = Field(description="Segundos entre a leitura e o momento da resposta")
    offline: bool = Field(description="Verdadeiro quando a idade passa de 30 s; a leitura não deve ser usada para decisão")


class Historico(BaseModel):
    tag: str
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
