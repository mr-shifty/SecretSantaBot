from aiogram.fsm.state import StatesGroup, State

class Route1States(StatesGroup):
    email = State()
    phone = State()
    address = State()
    delivery = State()
    wishlist = State()

class Route2States(StatesGroup):
    email = State()
    phone = State()
