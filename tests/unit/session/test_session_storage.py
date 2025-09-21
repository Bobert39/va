"""
Unit tests for session storage implementations.

Tests both Redis-based and in-memory session storage for OAuth sessions.
"""

import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.services.session_storage import InMemorySessionStorage, SessionStorage


class TestSessionStorage:
    """Test cases for Redis-based session storage."""

    @pytest.fixture
    def session_storage(self):
        """Create session storage instance for testing."""
        return SessionStorage(redis_url="redis://localhost:6379/1")  # Use test DB

    @pytest.fixture
    def sample_session_data(self):
        """Sample session data for testing."""
        return {
            "code_verifier": "test_code_verifier_12345",
            "timestamp": datetime.utcnow().isoformat(),
            "user_agent": "test-browser/1.0",
        }

    @pytest.mark.asyncio
    async def test_session_lifecycle(self, session_storage, sample_session_data):
        """Test complete session lifecycle: create, retrieve, delete."""
        state = "test_state_12345"

        # Mock Redis operations
        with patch("aioredis.from_url") as mock_redis_factory:
            mock_redis = AsyncMock()
            mock_redis_factory.return_value = mock_redis
            session_storage._redis = mock_redis  # Pre-set to avoid connection
            session_storage._redis = mock_redis  # Pre-set to avoid connection

            # Test storing session
            mock_redis.setex.return_value = True
            result = await session_storage.set_session(state, sample_session_data)
            assert result is True

            # Test retrieving session
            mock_redis.get.return_value = json.dumps(sample_session_data)
            retrieved_data = await session_storage.get_session(state)
            assert retrieved_data == sample_session_data

            # Test session exists
            mock_redis.exists.return_value = 1
            exists = await session_storage.exists(state)
            assert exists is True

            # Test deleting session
            mock_redis.delete.return_value = 1
            deleted = await session_storage.delete_session(state)
            assert deleted is True

            # Test session no longer exists
            mock_redis.get.return_value = None
            retrieved_after_delete = await session_storage.get_session(state)
            assert retrieved_after_delete is None

    @pytest.mark.asyncio
    async def test_session_timeout_update(self, session_storage):
        """Test updating session timeout."""
        state = "test_state_timeout"

        with patch("aioredis.from_url") as mock_redis_factory:
            mock_redis = AsyncMock()
            mock_redis_factory.return_value = mock_redis
            session_storage._redis = mock_redis  # Pre-set to avoid connection
            session_storage._redis = mock_redis  # Pre-set to avoid connection

            # Test setting timeout
            mock_redis.expire.return_value = True
            result = await session_storage.set_session_timeout(state, 7200)
            assert result is True

    @pytest.mark.asyncio
    async def test_redis_connection_failure(self, sample_session_data):
        """Test behavior when Redis connection fails."""
        # Create fresh session storage to test connection failure
        test_storage = SessionStorage()
        state = "test_state_failure"

        with patch("aioredis.from_url") as mock_redis_factory:
            mock_redis_factory.side_effect = ConnectionError("Redis unavailable")

            # Operations should return False on connection failure
            result = await test_storage.set_session(state, sample_session_data)
            assert result is False

            retrieved = await test_storage.get_session(state)
            assert retrieved is None

            exists = await test_storage.exists(state)
            assert exists is False

    @pytest.mark.asyncio
    async def test_health_check(self, session_storage):
        """Test Redis health check."""
        with patch("aioredis.from_url") as mock_redis_factory:
            mock_redis = AsyncMock()
            mock_redis_factory.return_value = mock_redis
            session_storage._redis = mock_redis  # Pre-set to avoid connection
            session_storage._redis = mock_redis  # Pre-set to avoid connection

            # Test healthy connection
            mock_redis.ping.return_value = True
            health = await session_storage.health_check()
            assert health is True

            # Test unhealthy connection
            mock_redis.ping.side_effect = ConnectionError("Redis down")
            health = await session_storage.health_check()
            assert health is False

    @pytest.mark.asyncio
    async def test_automatic_timestamp_addition(self, session_storage):
        """Test that timestamp is automatically added if missing."""
        state = "test_state_timestamp"
        data_without_timestamp = {"code_verifier": "test_verifier"}

        with patch("aioredis.from_url") as mock_redis_factory:
            mock_redis = AsyncMock()
            mock_redis_factory.return_value = mock_redis
            session_storage._redis = mock_redis  # Pre-set to avoid connection
            mock_redis.setex.return_value = True

            await session_storage.set_session(state, data_without_timestamp)

            # Verify timestamp was added
            call_args = mock_redis.setex.call_args
            stored_data = json.loads(call_args[0][2])  # Third argument is the JSON data
            assert "timestamp" in stored_data
            assert "code_verifier" in stored_data


class TestInMemorySessionStorage:
    """Test cases for in-memory session storage fallback."""

    @pytest.fixture
    def memory_storage(self):
        """Create in-memory session storage instance."""
        return InMemorySessionStorage()

    @pytest.fixture
    def sample_session_data(self):
        """Sample session data for testing."""
        return {
            "code_verifier": "memory_test_verifier",
            "timestamp": datetime.utcnow().isoformat(),
        }

    @pytest.mark.asyncio
    async def test_memory_session_lifecycle(self, memory_storage, sample_session_data):
        """Test complete session lifecycle in memory."""
        state = "memory_test_state"

        # Test storing session
        result = await memory_storage.set_session(state, sample_session_data, ttl=300)
        assert result is True

        # Test retrieving session
        retrieved = await memory_storage.get_session(state)
        assert retrieved == sample_session_data

        # Test session exists
        exists = await memory_storage.exists(state)
        assert exists is True

        # Test deleting session
        deleted = await memory_storage.delete_session(state)
        assert deleted is True

        # Test session no longer exists
        exists_after_delete = await memory_storage.exists(state)
        assert exists_after_delete is False

    @pytest.mark.asyncio
    async def test_memory_session_expiration(self, memory_storage):
        """Test session expiration in memory storage."""
        state = "expiring_state"
        data = {"code_verifier": "expiring_verifier"}

        # Store session with 1 second TTL
        await memory_storage.set_session(state, data, ttl=1)

        # Session should exist immediately
        exists_before = await memory_storage.exists(state)
        assert exists_before is True

        # Mock time advancement to trigger expiration
        with patch("src.services.session_storage.datetime") as mock_datetime:
            # Set current time to 2 seconds in the future
            future_time = datetime.utcnow() + timedelta(seconds=2)
            mock_datetime.utcnow.return_value = future_time

            # Session should be expired and removed
            exists_after = await memory_storage.exists(state)
            assert exists_after is False

            retrieved = await memory_storage.get_session(state)
            assert retrieved is None

    @pytest.mark.asyncio
    async def test_memory_cleanup_expired_sessions(self, memory_storage):
        """Test cleanup of expired sessions."""
        # Create multiple sessions with different expiration times
        states = ["state1", "state2", "state3"]
        data = {"code_verifier": "test"}

        # Store sessions
        await memory_storage.set_session(states[0], data, ttl=1)  # Expires soon
        await memory_storage.set_session(states[1], data, ttl=3600)  # Long-lived
        await memory_storage.set_session(states[2], data, ttl=1)  # Expires soon

        # Mock time advancement
        with patch("src.services.session_storage.datetime") as mock_datetime:
            future_time = datetime.utcnow() + timedelta(seconds=2)
            mock_datetime.utcnow.return_value = future_time

            # Run cleanup
            await memory_storage.cleanup_expired_sessions()

            # Only the long-lived session should remain
            assert not await memory_storage.exists(states[0])
            assert await memory_storage.exists(states[1])
            assert not await memory_storage.exists(states[2])

    @pytest.mark.asyncio
    async def test_memory_timeout_update(self, memory_storage, sample_session_data):
        """Test updating session timeout in memory."""
        state = "timeout_test_state"

        # Store session
        await memory_storage.set_session(state, sample_session_data, ttl=300)

        # Update timeout
        result = await memory_storage.set_session_timeout(state, 600)
        assert result is True

        # Try to update non-existent session
        result = await memory_storage.set_session_timeout("nonexistent", 600)
        assert result is False

    @pytest.mark.asyncio
    async def test_memory_health_check(self, memory_storage):
        """Test health check for in-memory storage."""
        health = await memory_storage.health_check()
        assert health is True  # Always healthy

    @pytest.mark.asyncio
    async def test_memory_no_op_methods(self, memory_storage):
        """Test no-op methods for memory storage."""
        # Connect and disconnect should not raise errors
        await memory_storage.connect()
        await memory_storage.disconnect()


class TestSessionStorageEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_invalid_json_handling(self):
        """Test handling of invalid JSON in Redis."""
        session_storage = SessionStorage()
        state = "invalid_json_state"

        with patch("aioredis.from_url") as mock_redis_factory:
            mock_redis = AsyncMock()
            mock_redis_factory.return_value = mock_redis
            session_storage._redis = mock_redis  # Pre-set to avoid connection

            # Mock Redis returning invalid JSON
            mock_redis.get.return_value = "invalid json data"

            result = await session_storage.get_session(state)
            assert result is None

    @pytest.mark.asyncio
    async def test_redis_operation_exceptions(self):
        """Test handling of Redis operation exceptions."""
        session_storage = SessionStorage()
        state = "exception_state"
        data = {"test": "data"}

        with patch("aioredis.from_url") as mock_redis_factory:
            mock_redis = AsyncMock()
            mock_redis_factory.return_value = mock_redis
            session_storage._redis = mock_redis  # Pre-set to avoid connection

            # Test setex exception
            mock_redis.setex.side_effect = Exception("Redis error")
            result = await session_storage.set_session(state, data)
            assert result is False

            # Test get exception
            mock_redis.get.side_effect = Exception("Redis error")
            result = await session_storage.get_session(state)
            assert result is None

            # Test delete exception
            mock_redis.delete.side_effect = Exception("Redis error")
            result = await session_storage.delete_session(state)
            assert result is False

            # Test exists exception
            mock_redis.exists.side_effect = Exception("Redis error")
            result = await session_storage.exists(state)
            assert result is False

    @pytest.mark.asyncio
    async def test_session_reuse_across_server_restarts(self):
        """Test that Redis sessions survive server restarts (mock scenario)."""
        # This tests the main advantage of Redis over in-memory storage
        session_storage = SessionStorage()
        state = "persistent_state"
        data = {"code_verifier": "persistent_verifier"}

        with patch("aioredis.from_url") as mock_redis_factory:
            mock_redis = AsyncMock()
            mock_redis_factory.return_value = mock_redis
            session_storage._redis = mock_redis  # Pre-set to avoid connection

            # Store session
            mock_redis.setex.return_value = True
            await session_storage.set_session(state, data)

            # Simulate server restart by creating new storage instance
            new_storage = SessionStorage()
            new_storage._redis = mock_redis  # Pre-set to avoid connection

            # Mock Redis still has the data
            mock_redis.get.return_value = json.dumps(data)
            retrieved = await new_storage.get_session(state)
            assert retrieved == data

    @pytest.mark.asyncio
    async def test_multi_instance_session_sharing(self):
        """Test session sharing between multiple server instances."""
        # Create two storage instances (simulating different server instances)
        storage1 = SessionStorage(redis_url="redis://localhost:6379/1")
        storage2 = SessionStorage(redis_url="redis://localhost:6379/1")

        state = "shared_state"
        data = {"code_verifier": "shared_verifier"}

        with patch("aioredis.from_url") as mock_redis_factory:
            mock_redis = AsyncMock()
            mock_redis_factory.return_value = mock_redis

            # Set up both instances to use the same mock
            storage1._redis = mock_redis
            storage2._redis = mock_redis

            # Instance 1 stores session
            mock_redis.setex.return_value = True
            await storage1.set_session(state, data)

            # Instance 2 retrieves same session
            mock_redis.get.return_value = json.dumps(data)
            retrieved = await storage2.get_session(state)
            assert retrieved == data

            # Instance 2 deletes session
            mock_redis.delete.return_value = 1
            deleted = await storage2.delete_session(state)
            assert deleted is True


if __name__ == "__main__":
    pytest.main([__file__])
