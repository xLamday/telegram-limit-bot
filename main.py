"""
Antispam Bot — entry point
"""

import asyncio
import logging

from telethon import TelegramClient

from config.settings import CFG
from bot.handlers import register_handlers
from bot.mute_queue import MuteQueue

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("antispam.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("antispam.main")


async def main():
    client = TelegramClient(CFG.session_name, CFG.api_id, CFG.api_hash)
    await client.start()

    me = await client.get_me()
    logger.info(f"Bot avviato come: {me.first_name} (id={me.id})")

    mute_queue = MuteQueue(client)
    asyncio.create_task(mute_queue.run())

    register_handlers(client, mute_queue, me.id)

    logger.info("In ascolto… (Ctrl+C per uscire)")
    try:
        await client.run_until_disconnected()
    except KeyboardInterrupt:
        logger.info("Shutdown richiesto.")
    finally:
        await client.disconnect()
        logger.info("Client disconnesso. Bye!")


if __name__ == "__main__":
    asyncio.run(main())
