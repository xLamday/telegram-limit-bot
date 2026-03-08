"""
Configurazione centralizzata del bot.
"""

from dataclasses import dataclass, field
from typing import List

@dataclass
class Config:
    # Credenziali Telegram — ottieni da https://my.telegram.org
    api_id: int         = 26831785
    api_hash: str       = "46f5f5e61c5ca3f67796c237d5a00260"
    session_name: str   = "antispam"

    # ID Telegram dell'amministratore del bot
    admin_id: List[int]       = field(default_factory=lambda: [961492841, 8218960547])

    # Percorso del database SQLite
    db_path: str        = "antispam.db"

    # Ore di mute per utenti limitati
    mute_hours: int     = 72

    # Secondi di pausa tra un'operazione di mute e la successiva (anti-flood)
    mute_rate_limit: float = 1.5

    # Finestra di deduplicazione messaggi per utente (secondi)
    dedup_window: float = 12.5


CFG = Config()
