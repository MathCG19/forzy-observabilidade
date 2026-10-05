import sqlite3
import threading
from pathlib import Path

COLUNAS = (
    "timestamp_utc", "session_id", "feature", "metodo", "rota", "tag", "status_code",
    "latencia_ms", "headers_completos", "idade_dado_s", "completude", "qtd_registros",
    "intervalo_medio_s", "intervalo_max_s", "severidade", "tamanho_resposta_bytes",
    "erro", "user_agent",
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS chamadas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp_utc TEXT NOT NULL,
    session_id TEXT NOT NULL,
    feature TEXT NOT NULL,
    metodo TEXT NOT NULL,
    rota TEXT NOT NULL,
    tag TEXT,
    status_code INTEGER NOT NULL,
    latencia_ms REAL NOT NULL,
    headers_completos INTEGER NOT NULL,
    idade_dado_s REAL,
    completude REAL,
    qtd_registros INTEGER,
    intervalo_medio_s REAL,
    intervalo_max_s REAL,
    severidade TEXT,
    tamanho_resposta_bytes INTEGER,
    erro TEXT,
    user_agent TEXT
);
CREATE INDEX IF NOT EXISTS ix_chamadas_ts ON chamadas (timestamp_utc);
CREATE INDEX IF NOT EXISTS ix_chamadas_feature ON chamadas (feature);
"""


class ObservabilidadeStore:
    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._conectar() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(SCHEMA)

    def _conectar(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=5)
        conn.row_factory = sqlite3.Row
        return conn

    def inserir(self, registro: dict) -> int:
        valores = [registro.get(c) for c in COLUNAS]
        sql = f"INSERT INTO chamadas ({', '.join(COLUNAS)}) VALUES ({', '.join('?' * len(COLUNAS))})"
        with self._lock, self._conectar() as conn:
            return conn.execute(sql, valores).lastrowid

    def listar(
        self,
        feature: str | None = None,
        session_id: str | None = None,
        desde: str | None = None,
        ate: str | None = None,
        limite: int | None = None,
    ) -> list[dict]:
        """Registros em ordem cronológica. Com `limite`, devolve os mais recentes."""
        filtros, params = [], []
        if feature:
            filtros.append("feature = ?")
            params.append(feature)
        if session_id:
            filtros.append("session_id = ?")
            params.append(session_id)
        if desde:
            filtros.append("timestamp_utc >= ?")
            params.append(desde)
        if ate:
            filtros.append("timestamp_utc <= ?")
            params.append(ate)
        where = f"WHERE {' AND '.join(filtros)}" if filtros else ""
        sql = f"SELECT * FROM chamadas {where} ORDER BY id DESC"
        if limite:
            sql += " LIMIT ?"
            params.append(limite)
        with self._conectar() as conn:
            linhas = conn.execute(sql, params).fetchall()
        registros = [dict(linha) for linha in reversed(linhas)]
        for r in registros:
            r["headers_completos"] = bool(r["headers_completos"])
        return registros
