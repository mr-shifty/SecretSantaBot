"""Basic unit tests for core functions."""
import pytest
from bot.utils import is_valid_email


def test_valid_email():
	assert is_valid_email("user@example.com") is True
	assert is_valid_email("john.doe+tag@sub.domain.co.uk") is True


def test_invalid_email():
	assert is_valid_email("invalid") is False
	assert is_valid_email("@example.com") is False
	assert is_valid_email("user@") is False
	assert is_valid_email("user @example.com") is False


if __name__ == "__main__":
	pytest.main([__file__, "-v"])
