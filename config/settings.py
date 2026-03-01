"""
Configurazione centralizzata del bot.
"""

from dataclasses import dataclass


@dataclass
class Config:
    # Credenziali Telegram — ottieni da https://my.telegram.org
    api_id: int         = 26831785
    api_hash: str       = "46f5f5e61c5ca3f67796c237d5a00260"
    session_name: str   = "antispam"

    # ID Telegram dell'amministratore del bot
    admin_id: int       = 961492841

    # Percorso del database SQLite
    db_path: str        = "antispam.db"

    # Ore di mute per utenti limitati
    mute_hours: int     = 72

    # Secondi di pausa tra un'operazione di mute e la successiva (anti-flood)
    mute_rate_limit: float = 0.5

    # Finestra di deduplicazione messaggi per utente (secondi)
    dedup_window: float = 5.0


CFG = Config()
