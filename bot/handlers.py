"""
Registra tutti gli handler (comandi + messaggi) sul client Telegram.
"""

from telethon import TelegramClient

from bot.commands import register_commands
from bot.messages import register_message_handler
from bot.mute_queue import MuteQueue


def register_handlers(client: TelegramClient, mute_queue: MuteQueue, me_id: int):
    """Entry point unico per registrare handler comandi e messaggi."""
    register_commands(client, mute_queue)
    register_message_handler(client, mute_queue, me_id)
