"""Unit tests for Secret Santa Bot."""
import pytest
from bot.utils import is_valid_email


def test_valid_emails():
	"""Test valid email formats."""
	valid_emails = [
		"user@example.com",
		"john.doe@company.co.uk",
		"test+tag@sub.domain.org",
		"a@b.c"
	]
	for email in valid_emails:
		assert is_valid_email(email), f"{email} should be valid"


def test_invalid_emails():
	"""Test invalid email formats."""
	invalid_emails = [
		"invalid",
		"@example.com",
		"user@",
		"user @example.com",
		"user@example",
		"user example@com"
	]
	for email in invalid_emails:
		assert not is_valid_email(email), f"{email} should be invalid"
