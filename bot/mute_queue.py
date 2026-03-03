"""
Coda asincrona per operazioni di mute.

Design:
- asyncio.Semaphore limita la concorrenza massima verso le API Telegram
- Backoff esponenziale con jitter su ogni errore generico
- FloodWaitError gestito globalmente: mette in pausa l'intero semaphore
  per evitare di martellare Telegram con altre richieste durante il flood
- Retry separati per FloodWait (illimitati, aspettiamo sempre) e
  per errori transitori (max MAX_RETRIES tentativi)
"""

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Optional

from telethon import TelegramClient
from telethon.errors import (
    FloodWaitError,
    UserAdminInvalidError,
    ChatAdminRequiredError,
    UserNotParticipantError,
)

from config.settings import CFG
from db import db

logger = logging.getLogger("antispam.mute_queue")

# Concorrenza massima verso Telegram (quante edit_permissions in parallelo)
_SEMAPHORE_LIMIT = 3
# Tentativi massimi per errori non-flood
_MAX_RETRIES = 4
# Base del backoff esponenziale in secondi
_BACKOFF_BASE = 2.0
# Jitter massimo aggiunto al backoff (evita thundering herd)
_JITTER_MAX = 1.5


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
        # Semaphore creato in run() dopo che il loop è già avviato
        self._sem: Optional[asyncio.Semaphore] = None
        # Lock globale per pausare tutto durante un FloodWait prolungato
        self._flood_lock: Optional[asyncio.Lock] = None

    async def enqueue(self, task: MuteTask):
        await self._queue.put(task)

    async def run(self):
        self._sem = asyncio.Semaphore(_SEMAPHORE_LIMIT)
        self._flood_lock = asyncio.Lock()
        logger.info(f"MuteQueue avviata (semaphore={_SEMAPHORE_LIMIT}).")

        while True:
            task: MuteTask = await self._queue.get()
            # Lancia ogni task in modo concorrente, il semaphore ne limita il numero
            asyncio.create_task(self._safe_process(task))

    async def _safe_process(self, task: MuteTask):
        try:
            await self._process(task)
        except Exception as e:
            logger.error(f"Errore imprevisto per user {task.user_id}: {e}")
        finally:
            self._queue.task_done()

    async def _process(self, task: MuteTask):
        for attempt in range(_MAX_RETRIES):
            # Se c'è un flood globale in corso, aspettiamo che si sblocchi
            async with self._flood_lock:
                pass

            try:
                async with self._sem:
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
                # FloodWait: acquisisce il flood_lock per bloccare TUTTI i worker
                # finché Telegram non è pronto a ricevere richieste
                wait = e.seconds + 5
                logger.warning(f"⏳ FloodWait {wait}s — pausa globale della coda.")
                if not self._flood_lock.locked():
                    async with self._flood_lock:
                        await asyncio.sleep(wait)
                else:
                    await asyncio.sleep(wait)
                # Non brucia un tentativo: il flood non è colpa nostra
                continue

            except (UserAdminInvalidError, ChatAdminRequiredError, UserNotParticipantError):
                logger.warning(f"🚫 Impossibile mutare {task.user_id} (admin/non-partecipante) — skip.")
                return

            except Exception as e:
                jitter = random.uniform(0, _JITTER_MAX)
                backoff = _BACKOFF_BASE ** attempt + jitter
                logger.warning(
                    f"⚠️ Errore mute {task.user_id} "
                    f"(attempt {attempt + 1}/{_MAX_RETRIES}): {e} "
                    f"— retry in {backoff:.1f}s"
                )
                await asyncio.sleep(backoff)

        logger.error(f"❌ Mute fallito definitivamente per user {task.user_id} dopo {_MAX_RETRIES} tentativi.")

    async def _send_reply(self, task: MuteTask):
        try:
            sender = await task.reply_event.get_sender()
            name = getattr(sender, "first_name", str(task.user_id))
            await task.reply_event.reply(
                f"🔇 {name} limitato per {CFG.mute_hours} ore."
            )
        except Exception as e:
            logger.debug(f"Impossibile inviare reply per {task.user_id}: {e}")
