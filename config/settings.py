"""
Configurazione centralizzata del bot.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from typing import Iterable

@dataclass
class Config:
    """
    Configurazione runtime.

    Best practice:
    - Impostare credenziali/ID via variabili d'ambiente (evita segreti nel repo)
    - Lasciare i default sensati per lo sviluppo locale

    Variabili supportate:
    - TELEGRAM_API_ID (int)
    - TELEGRAM_API_HASH (str)
    - TELEGRAM_SESSION (str)
    - TELEGRAM_ADMIN_IDS (csv di int: "123,456")
    - ANTISPAM_DB_PATH (str)
    - ANTISPAM_MUTE_HOURS (int)
    - ANTISPAM_MUTE_RATE_LIMIT (float)
    - ANTISPAM_DEDUP_WINDOW (float)
    """

    # Credenziali Telegram — ottieni da https://my.telegram.org
    # Nota: per evitare segreti nel repo, preferisci variabili d'ambiente.
    # I default qui sotto sono un fallback locale e possono essere rimossi
    # prima di pubblicare il progetto.
    api_id: int = 26831785
    api_hash: str = "46f5f5e61c5ca3f67796c237d5a00260"
    session_name: str = "antispam"

    # ID Telegram dell'amministratore del bot
    admin_ids: list[int] = field(default_factory=lambda: [961492841])

    # Percorso del database SQLite
    db_path: str = "antispam.db"

    # Ore di mute per utenti limitati
    mute_hours: int = 72

    # Secondi di pausa tra un'operazione di mute e la successiva (anti-flood)
    mute_rate_limit: float = 1.5

    # Finestra di deduplicazione messaggi per utente (secondi)
    dedup_window: float = 12.5

    @classmethod
    def from_env(cls) -> "Config":
        """Costruisce la config leggendo variabili d'ambiente (con fallback ai default)."""

        def _get_int(name: str, default: int) -> int:
            raw = os.getenv(name)
            if raw is None or raw.strip() == "":
                return default
            try:
                return int(raw)
            except ValueError:
                return default

        def _get_float(name: str, default: float) -> float:
            raw = os.getenv(name)
            if raw is None or raw.strip() == "":
                return default
            try:
                return float(raw)
            except ValueError:
                return default

        def _get_str(name: str, default: str) -> str:
            raw = os.getenv(name)
            return default if raw is None else raw

        def _parse_admin_ids(raw: str | None) -> list[int]:
            if not raw:
                return []
            ids: list[int] = []
            for part in raw.split(","):
                part = part.strip()
                if not part:
                    continue
                try:
                    ids.append(int(part))
                except ValueError:
                    continue
            return ids

        cfg = cls(
            api_id=_get_int("TELEGRAM_API_ID", cls().api_id),
            api_hash=_get_str("TELEGRAM_API_HASH", cls().api_hash),
            session_name=_get_str("TELEGRAM_SESSION", cls().session_name),
            admin_ids=_parse_admin_ids(os.getenv("TELEGRAM_ADMIN_IDS")) or list(cls().admin_ids),
            db_path=_get_str("ANTISPAM_DB_PATH", cls().db_path),
            mute_hours=_get_int("ANTISPAM_MUTE_HOURS", cls().mute_hours),
            mute_rate_limit=_get_float("ANTISPAM_MUTE_RATE_LIMIT", cls().mute_rate_limit),
            dedup_window=_get_float("ANTISPAM_DEDUP_WINDOW", cls().dedup_window),
        )
        return cfg

    def is_superadmin(self, user_id: int | None) -> bool:
        """True se `user_id` è uno degli admin configurati."""
        return user_id is not None and user_id in self.admin_ids

    def iter_admin_ids(self) -> Iterable[int]:
        """Itera gli admin_id configurati (filtrati/normalizzati)."""
        # Evita duplicati mantenendo ordine di inserimento
        seen: set[int] = set()
        for uid in self.admin_ids:
            if uid in seen:
                continue
            seen.add(uid)
            yield uid

    @property
    def primary_admin_id(self) -> int | None:
        """Admin di riferimento per notifiche in privato (primo della lista)."""
        for uid in self.iter_admin_ids():
            return uid
        return None

CFG = Config.from_env()
