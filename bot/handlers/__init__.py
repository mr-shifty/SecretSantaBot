"""Handler registration package."""
from . import route1, route2, admin, start


def register_all(dp):
    """Register all routers on Dispatcher `dp`."""
    dp.include_router(start.router)
    dp.include_router(route1.router)
    dp.include_router(route2.router)
    dp.include_router(admin.router)
