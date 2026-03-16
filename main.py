"""
Antispam Bot — entry point
"""

import asyncio
import contextlib

from telethon import TelegramClient

from config.settings import CFG
from bot.handlers import register_handlers
from loggerinfo import LoggerInfo
from bot.mute_queue import MuteQueue

logger = LoggerInfo(name="main").get_logger()


async def main():
    """Avvia il client Telethon, registra handler e resta in ascolto finché non disconnesso."""

    # Validazione config di sicurezza: blocca avvio se i dati sensibili sono mancanti/errati.
    api_id_str = str(CFG.api_id)
    errors: list[str] = []

    if CFG.api_id <= 0:
        errors.append("TELEGRAM_API_ID mancante o non valido (deve essere un intero > 0).")
    elif len(api_id_str) < 8:
        errors.append("TELEGRAM_API_ID troppo corto (almeno 8 cifre).")

    if not CFG.api_hash:
        errors.append("TELEGRAM_API_HASH mancante (stringa non vuota).")
    elif len(CFG.api_hash) < 32:
        errors.append("TELEGRAM_API_HASH troppo corto (almeno 32 caratteri).")

    if not any(CFG.iter_admin_ids()):
        errors.append("TELEGRAM_ADMIN_IDS non configurato (almeno un ID admin richiesto).")

    if errors:
        logger.error(
            "Configurazione non valida. Crea/aggiorna il file .env "
            "(puoi partire da .env.sample):\n- " + "\n- ".join(errors)
        )
        return

    client = TelegramClient(CFG.session_name, CFG.api_id, CFG.api_hash)
    await client.start()

    me = await client.get_me()
    logger.info(f"Bot avviato come: {me.first_name} (id={me.id})")

    mute_queue = MuteQueue(client)
    mute_task = asyncio.create_task(mute_queue.run(), name="mute-queue")

    register_handlers(client, mute_queue, me.id)

    logger.info("In ascolto… (Ctrl+C per uscire)")
    try:
        await client.run_until_disconnected()
    except KeyboardInterrupt:
        logger.info("Shutdown richiesto.")
    finally:
        mute_task.cancel()
        with contextlib.suppress(Exception):
            await mute_task
        await client.disconnect()
        logger.info("Client disconnesso. Bye!")


if __name__ == "__main__":
    asyncio.run(main())
