import os
import uuid

import requests

API_URL_PADRAO = os.getenv("FORZY_API_URL", "http://127.0.0.1:8000")


class ErroApi(Exception):
    def __init__(self, mensagem: str, status: int | None = None):
        super().__init__(mensagem)
        self.status = status


class ApiClient:
    """Cliente da Sensor Monitoring API. Toda chamada leva X-Session-Id e X-Feature."""

    def __init__(self, base_url: str = API_URL_PADRAO, session_id: str | None = None, timeout: float = 10):
        self.base_url = base_url.rstrip("/")
        self.session_id = session_id or str(uuid.uuid4())
        self.timeout = timeout
        self.http = requests.Session()

    def _get(self, caminho: str, feature: str, params: dict | None = None):
        headers = {"X-Session-Id": self.session_id, "X-Feature": feature}
        try:
            resp = self.http.get(f"{self.base_url}{caminho}", params=params, headers=headers, timeout=self.timeout)
        except requests.ConnectionError as exc:
            raise ErroApi(f"Não foi possível conectar em {self.base_url}. A API está rodando?") from exc
        except requests.Timeout as exc:
            raise ErroApi(f"A API não respondeu em {self.timeout} s.") from exc
        if resp.status_code >= 400:
            try:
                detalhe = resp.json().get("detail")
            except ValueError:
                detalhe = resp.text
            raise ErroApi(f"{resp.status_code}: {detalhe}", resp.status_code)
        return resp.json()

    def sensores(self, feature: str) -> list[dict]:
        return self._get("/v1/sensores", feature)

    def leitura_atual(self, tag: str, feature: str = "tela-leitura-atual") -> dict:
        return self._get(f"/v1/sensores/{tag}/leitura-atual", feature)

    def historico(self, tag: str, inicio=None, fim=None, limite: int = 120, feature: str = "tela-historico") -> dict:
        params = {"limite": limite}
        if inicio:
            params["inicio"] = inicio.isoformat()
        if fim:
            params["fim"] = fim.isoformat()
        return self._get(f"/v1/sensores/{tag}/historico", feature, params)

    def observabilidade(self, feature: str = "tela-observabilidade", session_id: str | None = None,
                        filtro_feature: str | None = None, desde=None, limite: int = 500) -> dict:
        params = {"limite": limite}
        if session_id:
            params["session_id"] = session_id
        if filtro_feature:
            params["feature"] = filtro_feature
        if desde:
            params["desde"] = desde.isoformat()
        return self._get("/v1/observabilidade", feature, params)

    def resumo(self, feature: str = "tela-observabilidade", desde=None) -> dict:
        params = {"desde": desde.isoformat()} if desde else None
        return self._get("/v1/observabilidade/resumo", feature, params)
