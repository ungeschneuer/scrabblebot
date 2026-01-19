"""Unit tests for rate limiting functionality."""

import pytest
import time
from main import RateLimiter


class TestRateLimiter:
    """Tests for RateLimiter class."""

    def test_rate_limiter_initialization(self):
        """Test rate limiter initializes correctly."""
        limiter = RateLimiter(max_requests=5, time_window=60, enabled=True)
        assert limiter.max_requests == 5
        assert limiter.time_window == 60
        assert limiter.enabled is True
        assert len(limiter.requests) == 0

    def test_rate_limiter_disabled(self):
        """Test that disabled rate limiter always allows requests."""
        limiter = RateLimiter(max_requests=1, time_window=60, enabled=False)

        # Should allow unlimited requests when disabled
        for i in range(10):
            assert limiter.is_allowed("user1") is True

    def test_rate_limiter_allows_within_limit(self):
        """Test that requests within limit are allowed."""
        limiter = RateLimiter(max_requests=3, time_window=60, enabled=True)

        # First 3 requests should be allowed
        assert limiter.is_allowed("user1") is True
        assert limiter.is_allowed("user1") is True
        assert limiter.is_allowed("user1") is True

    def test_rate_limiter_blocks_over_limit(self):
        """Test that requests over limit are blocked."""
        limiter = RateLimiter(max_requests=3, time_window=60, enabled=True)

        # First 3 requests allowed
        for i in range(3):
            assert limiter.is_allowed("user1") is True

        # 4th request should be blocked
        assert limiter.is_allowed("user1") is False
        assert limiter.is_allowed("user1") is False

    def test_rate_limiter_different_users(self):
        """Test that different users have separate limits."""
        limiter = RateLimiter(max_requests=2, time_window=60, enabled=True)

        # User 1 makes 2 requests
        assert limiter.is_allowed("user1") is True
        assert limiter.is_allowed("user1") is True

        # User 2 should still be able to make requests
        assert limiter.is_allowed("user2") is True
        assert limiter.is_allowed("user2") is True

        # Both users should now be rate limited
        assert limiter.is_allowed("user1") is False
        assert limiter.is_allowed("user2") is False

    def test_rate_limiter_sliding_window(self):
        """Test that old requests are removed from sliding window."""
        limiter = RateLimiter(max_requests=2, time_window=1, enabled=True)

        # Make 2 requests
        assert limiter.is_allowed("user1") is True
        assert limiter.is_allowed("user1") is True

        # Should be rate limited
        assert limiter.is_allowed("user1") is False

        # Wait for time window to pass
        time.sleep(1.1)

        # Should be allowed again after window expires
        assert limiter.is_allowed("user1") is True

    def test_rate_limiter_cleanup(self):
        """Test cleanup of old entries."""
        limiter = RateLimiter(max_requests=5, time_window=1, enabled=True)

        # Add requests for multiple users
        limiter.is_allowed("user1")
        limiter.is_allowed("user2")
        limiter.is_allowed("user3")

        assert len(limiter.requests) == 3

        # Wait for time window to pass
        time.sleep(1.1)

        # Cleanup should remove all old entries
        limiter.cleanup_old_entries()
        assert len(limiter.requests) == 0

    def test_rate_limiter_partial_cleanup(self):
        """Test cleanup removes only old entries."""
        limiter = RateLimiter(max_requests=5, time_window=2, enabled=True)

        # Add request for user1
        limiter.is_allowed("user1")
        time.sleep(1)

        # Add request for user2 (newer)
        limiter.is_allowed("user2")

        # Wait so user1's request expires but user2's doesn't
        time.sleep(1.5)

        limiter.cleanup_old_entries()

        # user1 should be removed, user2 should remain
        assert "user1" not in limiter.requests
        assert "user2" in limiter.requests

    def test_rate_limiter_tracking_timestamps(self):
        """Test that timestamps are correctly tracked."""
        limiter = RateLimiter(max_requests=3, time_window=60, enabled=True)

        start_time = time.time()
        limiter.is_allowed("user1")
        limiter.is_allowed("user1")

        # Check that 2 timestamps were recorded
        assert len(limiter.requests["user1"]) == 2

        # Check timestamps are recent
        for timestamp in limiter.requests["user1"]:
            assert timestamp >= start_time
            assert timestamp <= time.time()
