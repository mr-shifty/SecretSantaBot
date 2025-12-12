"""Lightweight internal HTTP API for bot control (used by admin panel).

Provides a single secured endpoint to trigger reminders on-demand.
"""
import asyncio
import json
from aiohttp import web
from typing import Optional
from bot.config import BOT_INTERNAL_SECRET, BOT_INTERNAL_API_PORT
from bot.logger import get_logger
from bot.scheduler import send_assignment_reminders, send_registration_reminders

logger = get_logger("internal_api")

_runner: Optional[web.AppRunner] = None
_site: Optional[web.TCPSite] = None


async def _handle_trigger(request: web.Request):
    # simple token auth via header
    token = request.headers.get('X-Internal-Token')
    if not BOT_INTERNAL_SECRET or token != BOT_INTERNAL_SECRET:
        return web.json_response({'error': 'unauthorized'}, status=401)

    try:
        data = await request.json()
    except Exception:
        data = {}

    assignment = bool(data.get('assignment'))
    registration = bool(data.get('registration'))

    # call reminder functions and return counts
    result = {'assignment_sent': 0, 'registration_sent': 0}
    # We pass 'bot' via app['bot'] if set
    bot = request.app.get('bot')
    if assignment:
        try:
            n = await send_assignment_reminders(bot=bot)
            result['assignment_sent'] = int(n or 0)
        except Exception as exc:
            logger.exception(f"assignment trigger failed: {exc}")
    if registration:
        try:
            # manual trigger should force sending regardless of cutoff
            n = await send_registration_reminders(bot=bot, force=True)
            result['registration_sent'] = int(n or 0)
        except Exception as exc:
            logger.exception(f"registration trigger failed: {exc}")

    return web.json_response(result)


async def start_server(bot, host: str = '0.0.0.0', port: int = None):
    """Start aiohttp internal API server. Attach bot instance to app for sending messages."""
    global _runner, _site
    if port is None:
        port = BOT_INTERNAL_API_PORT or 9000
    app = web.Application()
    app.router.add_post('/internal/trigger_reminders', _handle_trigger)
    # attach bot so handlers can send messages
    app['bot'] = bot
    _runner = web.AppRunner(app)
    await _runner.setup()
    _site = web.TCPSite(_runner, host, port)
    await _site.start()
    logger.info(f"Internal API server started on {host}:{port}")


async def stop_server():
    global _runner, _site
    if _site:
        try:
            await _site.stop()
        except Exception:
            pass
        _site = None
    if _runner:
        try:
            await _runner.cleanup()
        except Exception:
            pass
        _runner = None
    logger.info("Internal API server stopped")
