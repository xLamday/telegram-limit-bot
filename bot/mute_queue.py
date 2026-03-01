"""
Coda asincrona per operazioni di mute — evita FloodWait verso Telegram.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from telethon import TelegramClient
from telethon.errors import FloodWaitError, UserAdminInvalidError, ChatAdminRequiredError

from config.settings import CFG
from db import db

logger = logging.getLogger("antispam.mute_queue")


@dataclass
class MuteTask:
    chat: object
    user_id: int
    group_id: int
    reply_event: Optional[object] = field(default=None)


class MuteQueue:
    def __init__(self, client: TelegramClient):
        self._client = client
        self._queue: asyncio.Queue = asyncio.Queue()

    async def enqueue(self, task: MuteTask):
        await self._queue.put(task)

    async def run(self):
        logger.info("MuteQueue avviata.")
        while True:
            task: MuteTask = await self._queue.get()
            try:
                await self._process(task)
            except Exception as e:
                logger.error(f"Errore imprevisto nel processing di {task.user_id}: {e}")
            finally:
                self._queue.task_done()
                # Pausa anti-flood tra un'operazione e la successiva
                await asyncio.sleep(CFG.mute_rate_limit)

    async def _process(self, task: MuteTask):
        max_retries = 3
        for attempt in range(max_retries):
            try:
                await self._client.edit_permissions(
                    task.chat,
                    task.user_id,
                    send_messages=False,
                    until_date=int(time.time()) + CFG.mute_hours * 3600,
                )
                db.set_user(task.group_id, task.user_id, "limited")
                logger.info(f"✅ Mutato user {task.user_id} in gruppo {task.group_id}")

                if task.reply_event:
                    await self._send_reply(task)
                return

            except FloodWaitError as e:
                wait = e.seconds + 5
                logger.warning(f"⏳ FloodWait {wait}s per user {task.user_id} — in attesa…")
                await asyncio.sleep(wait)
                # Non conta come tentativo fallito, ricominciamo il for
                continue

            except (UserAdminInvalidError, ChatAdminRequiredError):
                logger.warning(f"🚫 Impossibile mutare admin {task.user_id} — skip.")
                return

            except Exception as e:
                backoff = 2 ** attempt
                logger.warning(
                    f"⚠️ Errore mute {task.user_id} (attempt {attempt + 1}/{max_retries}): "
                    f"{e} — retry in {backoff}s"
                )
                await asyncio.sleep(backoff)

        logger.error(f"❌ Mute fallito definitivamente per user {task.user_id}")

    async def _send_reply(self, task: MuteTask):
        try:
            sender = await task.reply_event.get_sender()
            name = getattr(sender, "first_name", str(task.user_id))
            await task.reply_event.reply(
                f"🔇 {name} limitato per {CFG.mute_hours} ore."
            )
        except Exception as e:
            logger.debug(f"Impossibile inviare reply per {task.user_id}: {e}")
