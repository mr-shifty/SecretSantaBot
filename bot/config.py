from dotenv import load_dotenv
import os
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS","").split(",") if x]
REMINDER_HOURS = int(os.getenv("REMINDER_HOURS", "24"))
# Safety flag: when False (default) only ADMIN_IDS will actually receive messages
# SEND_REAL_NOTIFICATIONS = os.getenv("SEND_REAL_NOTIFICATIONS", "false").lower() in ("1", "true", "yes")
SEND_REAL_NOTIFICATIONS = True
