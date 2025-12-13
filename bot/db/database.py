"""Async DB engine and session factory."""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
from bot.db.models import Base
from bot.config import DATABASE_URL

engine = None
async_session = None


async def init_db(database_url: str | None = None):
	"""Initialize async engine and session factory. Creates tables if needed."""
	global engine, async_session
	url = database_url or DATABASE_URL
	if not url:
		raise RuntimeError("DATABASE_URL is not set")

	engine = create_async_engine(url, echo=False, future=True, poolclass=NullPool)
	async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

	# Create tables for development convenience (use Alembic in prod)
	async with engine.begin() as conn:
		await conn.run_sync(Base.metadata.create_all)


def get_session():
	if async_session is None:
		raise RuntimeError("Database not initialized. Call init_db first.")
	return async_session()
