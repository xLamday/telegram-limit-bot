"""
Configurazione centralizzata del bot.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Iterable

from dotenv import load_dotenv


def _ensure_env_sample() -> None:
    """
    Crea un file .env.sample con placeholder se non esiste.

    Non crea/modifica mai il vero .env, lascia che sia l'utente a copiarlo.
    """
    sample_path = Path(".env.sample")
    if sample_path.exists():
        return

    sample_content = """# Esempio di configurazione per il bot antispam
#
# Copia questo file in `.env` e sostituisci i valori con quelli reali.

TELEGRAM_API_ID=123456789        # intero, almeno 8 cifre
TELEGRAM_API_HASH=00000000000000000000000000000000  # stringa, almeno 32 caratteri
TELEGRAM_SESSION=antispam
TELEGRAM_ADMIN_IDS=961492841     # CSV di ID: 111,222,333

ANTISPAM_DB_PATH=antispam.db
ANTISPAM_MUTE_HOURS=72
ANTISPAM_MUTE_RATE_LIMIT=1.5
ANTISPAM_DEDUP_WINDOW=12.5
"""
    sample_path.write_text(sample_content, encoding="utf-8")


_ensure_env_sample()
# Carica variabili da .env (se presente) senza sovrascrivere quelle già
# presenti nell'ambiente.
load_dotenv(dotenv_path=".env", override=False)

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
    # I default sono volutamente "vuoti": l'utente DEVE valorizzarli via env.
    api_id: int = 0
    api_hash: str = ""
    session_name: str = "antispam"

    # ID Telegram degli amministratori del bot
    admin_ids: list[int] = field(default_factory=list)

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

        base = cls()

        cfg = cls(
            api_id=_get_int("TELEGRAM_API_ID", base.api_id),
            api_hash=_get_str("TELEGRAM_API_HASH", base.api_hash),
            session_name=_get_str("TELEGRAM_SESSION", base.session_name),
            admin_ids=_parse_admin_ids(os.getenv("TELEGRAM_ADMIN_IDS")) or list(base.admin_ids),
            db_path=_get_str("ANTISPAM_DB_PATH", base.db_path),
            mute_hours=_get_int("ANTISPAM_MUTE_HOURS", base.mute_hours),
            mute_rate_limit=_get_float("ANTISPAM_MUTE_RATE_LIMIT", base.mute_rate_limit),
            dedup_window=_get_float("ANTISPAM_DEDUP_WINDOW", base.dedup_window),
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
