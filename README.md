# Antispam Bot

Bot Telegram (userbot) per limitare automaticamente i nuovi utenti nei gruppi gestiti.

## Struttura del progetto

```
antispam_bot/
│
├── main.py                  # Entry point
├── requirements.txt
│
├── config/
│   ├── __init__.py
│   └── settings.py          # Tutte le configurazioni in un posto solo
│
├── db/
│   ├── __init__.py          # Espone l'istanza singleton `db`
│   └── database.py          # Classe Database — SQLite thread-safe con WAL
│
├── bot/
│   ├── __init__.py
│   ├── handlers.py          # Aggrega e registra tutti gli handler
│   ├── commands.py          # Handler dei comandi admin (/limita, /free, ecc.)
│   ├── messages.py          # Handler dei messaggi in entrata (auto-mute)
│   └── mute_queue.py        # Coda asincrona anti-flood per operazioni mute
│
└── utils/
    ├── __init__.py
    └── permissions.py       # Helper per controllo admin e permessi Telegram
```

## Installazione

```bash
pip install -r requirements.txt
python main.py
```

Al primo avvio Telethon chiederà numero di telefono e codice OTP.

## Comandi disponibili

| Comando | Descrizione |
|---|---|
| `/registragruppo` | Registra il gruppo attuale e muta tutti i membri non-admin |
| `/limita <username\|id>` | Muta manualmente un utente per N ore |
| `/free <username\|id>` | Libera permanentemente un utente |
| `/log` | Mostra lo stato di tutti gli utenti del gruppo |
| `/gruppi` | Lista tutti i gruppi registrati |

## Configurazione

Modifica `config/settings.py`:

```python
api_id   = ...          # da https://my.telegram.org
api_hash = "..."
admin_ids = [...]       # lista di user_id Telegram autorizzati (es. [123, 456])

mute_hours      = 72    # ore di mute per utenti limitati
mute_rate_limit = 0.5   # secondi di pausa tra un mute e il successivo
dedup_window    = 5.0   # ignora messaggi ripetuti dello stesso utente entro N secondi
```

In alternativa (consigliato), usa variabili d'ambiente:

- `TELEGRAM_API_ID`
- `TELEGRAM_API_HASH`
- `TELEGRAM_SESSION`
- `TELEGRAM_ADMIN_IDS` (csv: `123,456`)
- `ANTISPAM_DB_PATH`
- `ANTISPAM_MUTE_HOURS`
- `ANTISPAM_MUTE_RATE_LIMIT`
- `ANTISPAM_DEDUP_WINDOW`
