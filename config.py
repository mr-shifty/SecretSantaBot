from dotenv import load_dotenv
import os
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS","").split(",") if x]
REMINDER_HOURS = int(os.getenv("REMINDER_HOURS", "24"))
