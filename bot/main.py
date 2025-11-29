"""Entry point for the Telegram bot using aiogram v3."""
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from bot.config import BOT_TOKEN
from bot.db.database import init_db
from bot.handlers import register_all
from bot.scheduler import start_scheduler, stop_scheduler
from bot.logger import setup_logging, get_logger

logger = get_logger("main")


async def main():
	if not BOT_TOKEN:
		logger.error("BOT_TOKEN is not set in environment")
		raise RuntimeError("BOT_TOKEN is not set in environment")

	logger.info("Initializing Secret Santa Bot...")
	await init_db()
	logger.info("Database initialized successfully")

	bot = Bot(token=BOT_TOKEN)
	dp = Dispatcher(storage=MemoryStorage())

	# register handlers
	register_all(dp)
	logger.info("Handlers registered")

	# start background scheduler
	await start_scheduler(bot)
	logger.info("Background scheduler started")

	try:
		logger.info("Starting bot polling...")
		await dp.start_polling(bot)
	except Exception as e:
		logger.error(f"Error during polling: {e}", exc_info=True)
		raise
	finally:
		stop_scheduler()
		await bot.session.close()
		logger.info("Bot stopped")


if __name__ == "__main__":
	# Setup logging before running
	setup_logging("secret_santa")
	logger.info("=" * 60)
	logger.info("Secret Santa Bot started")
	logger.info("=" * 60)
	asyncio.run(main())
