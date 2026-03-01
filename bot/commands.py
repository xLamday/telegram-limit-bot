"""
Handlers dei comandi admin del bot.
"""

import logging
import time

from telethon import TelegramClient, events
from telethon.errors import FloodWaitError
import asyncio

from config.settings import CFG
from db import db
from utils.permissions import is_admin
from bot.mute_queue import MuteQueue, MuteTask

logger = logging.getLogger("antispam.commands")


def register_commands(client: TelegramClient, mute_queue: MuteQueue):

    # ── /registragruppo ────────────────────────────────────────────────────

    @client.on(events.NewMessage(pattern=r"/registragruppo"))
    async def cmd_registragruppo(event):
        if event.sender_id != CFG.admin_id:
            return await event.reply("❌ Non sei autorizzato.")

        chat = await event.get_chat()
        db.upsert_group(chat.id, chat.title)

        count = 0
        async for user in client.iter_participants(chat):
            if user.bot:
                continue
            if await is_admin(client, chat, user.id):
                continue
            existing = db.get_user_status(chat.id, user.id)
            if existing == "free":
                continue
            db.set_user(chat.id, user.id, "limited")
            await mute_queue.enqueue(MuteTask(chat, user.id, chat.id))
            count += 1

        await event.reply(
            f"✅ Gruppo <b>{chat.title}</b> registrato.\n"
            f"👥 {count} utenti accodati per mute.",
            parse_mode="html",
        )
        logger.info(f"Gruppo {chat.id} registrato. {count} utenti accodati.")

    # ── /limita ────────────────────────────────────────────────────────────

    @client.on(events.NewMessage(pattern=r"/limita (.+)"))
    async def cmd_limita(event):
        if event.sender_id != CFG.admin_id:
            return await event.reply("❌ Non sei autorizzato.")

        chat = await event.get_chat()
        target = event.pattern_match.group(1).strip()
        try:
            user = await client.get_entity(target)
            db.set_user(chat.id, user.id, "limited")
            await mute_queue.enqueue(MuteTask(chat, user.id, chat.id))
            await event.reply(f"🔇 {user.first_name} limitato per {CFG.mute_hours} ore.")
        except Exception as e:
            await event.reply(f"⚠️ Errore: {e}")

    # ── /free ──────────────────────────────────────────────────────────────

    @client.on(events.NewMessage(pattern=r"/free (.+)"))
    async def cmd_free(event):
        if event.sender_id != CFG.admin_id:
            return await event.reply("❌ Non sei autorizzato.")

        chat = await event.get_chat()
        target = event.pattern_match.group(1).strip()
        try:
            user = await client.get_entity(target)
            db.set_user(chat.id, user.id, "free")
            await client.edit_permissions(chat, user.id, send_messages=True)
            await event.reply(f"✅ {user.first_name} liberato permanentemente.")
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds)
            await event.reply("⚠️ Rate limit Telegram: riprova tra qualche secondo.")
        except Exception as e:
            await event.reply(f"⚠️ Errore: {e}")

    # ── /log ───────────────────────────────────────────────────────────────

    @client.on(events.NewMessage(pattern=r"/log"))
    async def cmd_log(event):
        if event.sender_id != CFG.admin_id:
            return await event.reply("❌ Non sei autorizzato.")

        chat = await event.get_chat()
        rows = db.list_users(chat.id)
        if not rows:
            return await event.reply("Nessun utente registrato per questo gruppo.")

        lines = ["📋 <b>Log utenti:</b>"]
        for row in rows:
            ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(row["updated_at"]))
            lines.append(f"  <code>{row['user_id']}</code> → {row['status']} ({ts})")

        msg = "\n".join(lines)
        if len(msg) > 4000:
            msg = msg[:4000] + "\n… (troncato)"
        await event.reply(msg, parse_mode="html")

    # ── /gruppi ────────────────────────────────────────────────────────────

    @client.on(events.NewMessage(pattern=r"/gruppi"))
    async def cmd_gruppi(event):
        if event.sender_id != CFG.admin_id:
            return await event.reply("❌ Non sei autorizzato.")

        groups = db.list_groups()
        if not groups:
            return await event.reply("Nessun gruppo registrato.")

        lines = ["🗂 <b>Gruppi registrati:</b>"]
        for g in groups:
            ts = time.strftime("%Y-%m-%d", time.localtime(g["registered_at"]))
            lines.append(f"  <code>{g['group_id']}</code> — {g['group_name']} (dal {ts})")
        await event.reply("\n".join(lines), parse_mode="html")
