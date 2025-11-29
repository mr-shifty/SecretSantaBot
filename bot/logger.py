"""Logging configuration for the Secret Santa Bot."""
import logging
import sys
from logging.handlers import RotatingFileHandler

def setup_logging(name: str = "secret_santa", log_file: str = "logs/app.log", level=logging.INFO):
	"""Setup logging with both file and console handlers."""
	
	logger = logging.getLogger(name)
	logger.setLevel(level)
	
	# Create logs directory if it doesn't exist
	import os
	os.makedirs("logs", exist_ok=True)
	
	# Console handler (stdout)
	console_handler = logging.StreamHandler(sys.stdout)
	console_handler.setLevel(level)
	console_format = logging.Formatter(
		"%(asctime)s - %(name)s - %(levelname)s - %(message)s",
		datefmt="%Y-%m-%d %H:%M:%S"
	)
	console_handler.setFormatter(console_format)
	
	# File handler (rotating)
	file_handler = RotatingFileHandler(
		log_file,
		maxBytes=10 * 1024 * 1024,  # 10 MB
		backupCount=5
	)
	file_handler.setLevel(level)
	file_format = logging.Formatter(
		"%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
		datefmt="%Y-%m-%d %H:%M:%S"
	)
	file_handler.setFormatter(file_format)
	
	# Add handlers to logger
	logger.addHandler(console_handler)
	logger.addHandler(file_handler)
	
	return logger


def get_logger(name: str) -> logging.Logger:
	"""Get logger for a specific module."""
	return logging.getLogger("secret_santa." + name)
