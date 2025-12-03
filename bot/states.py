from aiogram.fsm.state import StatesGroup, State

class Route1States(StatesGroup):
    # Initial steps
    email = State()
    phone = State()
    pickup_method = State()  # 'postal' or 'pickup'
    wishlist = State()
    
    # Postal delivery path
    postal_city = State()
    postal_street = State()
    postal_building = State()
    postal_corpus = State()
    postal_apartment = State()
    postal_fullname = State()
    postal_phone = State()
    postal_review = State()
    
    # Pickup point path
    pickup_company = State()
    pickup_address = State()
    pickup_fullname = State()
    pickup_phone = State()
    pickup_review = State()

class Route2States(StatesGroup):
    email = State()
    phone = State()
    review = State()
