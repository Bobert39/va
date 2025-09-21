"""
Redis-based session storage for OAuth sessions.

This module provides a secure, persistent session storage implementation
using Redis to replace the in-memory storage for production readiness.
"""

import json
import os
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import aioredis
from aioredis import Redis


class SessionStorage:
    """Redis-based session storage for OAuth sessions."""

    def __init__(self, redis_url: Optional[str] = None):
        """
        Initialize the session storage.

        Args:
            redis_url: Redis connection URL (defaults to environment variable or localhost)
        """
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379")
        self._redis: Optional[Redis] = None
        self._key_prefix = "oauth_session:"
        self._ttl = 3600  # 1 hour TTL for session data

    async def connect(self):
        """Connect to Redis."""
        if not self._redis:
            self._redis = await aioredis.from_url(
                self.redis_url, decode_responses=True, encoding="utf-8"
            )

    async def disconnect(self):
        """Disconnect from Redis."""
        if self._redis:
            await self._redis.close()
            self._redis = None

    async def set_session(
        self, state: str, data: Dict[str, Any], ttl: Optional[int] = None
    ) -> bool:
        """
        Store session data in Redis.

        Args:
            state: OAuth state parameter
            data: Session data to store
            ttl: Time to live in seconds (defaults to self._ttl)

        Returns:
            True if successful, False otherwise
        """
        await self.connect()

        key = f"{self._key_prefix}{state}"
        ttl = ttl or self._ttl

        try:
            # Add timestamp if not present
            if "timestamp" not in data:
                data["timestamp"] = datetime.utcnow().isoformat()

            # Serialize data to JSON
            json_data = json.dumps(data)

            # Store with expiration
            await self._redis.setex(key, ttl, json_data)
            return True

        except Exception as e:
            print(f"Error storing session: {e}")
            return False

    async def get_session(self, state: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve session data from Redis.

        Args:
            state: OAuth state parameter

        Returns:
            Session data if found, None otherwise
        """
        await self.connect()

        key = f"{self._key_prefix}{state}"

        try:
            json_data = await self._redis.get(key)

            if json_data:
                return json.loads(json_data)
            return None

        except Exception as e:
            print(f"Error retrieving session: {e}")
            return None

    async def delete_session(self, state: str) -> bool:
        """
        Delete session data from Redis.

        Args:
            state: OAuth state parameter

        Returns:
            True if successful, False otherwise
        """
        await self.connect()

        key = f"{self._key_prefix}{state}"

        try:
            result = await self._redis.delete(key)
            return result > 0

        except Exception as e:
            print(f"Error deleting session: {e}")
            return False

    async def exists(self, state: str) -> bool:
        """
        Check if session exists in Redis.

        Args:
            state: OAuth state parameter

        Returns:
            True if session exists, False otherwise
        """
        await self.connect()

        key = f"{self._key_prefix}{state}"

        try:
            return await self._redis.exists(key) > 0

        except Exception as e:
            print(f"Error checking session existence: {e}")
            return False

    async def set_session_timeout(self, state: str, ttl: int) -> bool:
        """
        Update session TTL/timeout.

        Args:
            state: OAuth state parameter
            ttl: New time to live in seconds

        Returns:
            True if successful, False otherwise
        """
        await self.connect()

        key = f"{self._key_prefix}{state}"

        try:
            result = await self._redis.expire(key, ttl)
            return result

        except Exception as e:
            print(f"Error setting session timeout: {e}")
            return False

    async def cleanup_expired_sessions(self):
        """
        Clean up expired sessions (handled automatically by Redis TTL).
        This method is here for completeness and testing.
        """
        # Redis automatically handles expiration via TTL
        pass

    async def health_check(self) -> bool:
        """
        Check Redis connection health.

        Returns:
            True if Redis is accessible, False otherwise
        """
        try:
            await self.connect()
            await self._redis.ping()
            return True
        except Exception as e:
            print(f"Redis health check failed: {e}")
            return False


# Global instance
session_storage = SessionStorage()


# In-memory fallback for development/testing when Redis is not available
class InMemorySessionStorage:
    """In-memory session storage fallback for development."""

    def __init__(self):
        """Initialize in-memory storage."""
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._timeouts: Dict[str, datetime] = {}

    async def connect(self):
        """No-op for in-memory storage."""
        pass

    async def disconnect(self):
        """No-op for in-memory storage."""
        pass

    async def set_session(
        self, state: str, data: Dict[str, Any], ttl: Optional[int] = None
    ) -> bool:
        """Store session in memory."""
        self._sessions[state] = data
        if ttl:
            self._timeouts[state] = datetime.utcnow() + timedelta(seconds=ttl)
        return True

    async def get_session(self, state: str) -> Optional[Dict[str, Any]]:
        """Retrieve session from memory."""
        # Check timeout
        if state in self._timeouts:
            if datetime.utcnow() > self._timeouts[state]:
                # Session expired
                del self._sessions[state]
                del self._timeouts[state]
                return None

        return self._sessions.get(state)

    async def delete_session(self, state: str) -> bool:
        """Delete session from memory."""
        if state in self._sessions:
            del self._sessions[state]
            if state in self._timeouts:
                del self._timeouts[state]
            return True
        return False

    async def exists(self, state: str) -> bool:
        """Check if session exists in memory."""
        # Check timeout
        if state in self._timeouts:
            if datetime.utcnow() > self._timeouts[state]:
                # Session expired
                del self._sessions[state]
                del self._timeouts[state]
                return False

        return state in self._sessions

    async def set_session_timeout(self, state: str, ttl: int) -> bool:
        """Update session timeout."""
        if state in self._sessions:
            self._timeouts[state] = datetime.utcnow() + timedelta(seconds=ttl)
            return True
        return False

    async def cleanup_expired_sessions(self):
        """Clean up expired sessions."""
        current_time = datetime.utcnow()
        expired = [
            state for state, timeout in self._timeouts.items() if current_time > timeout
        ]
        for state in expired:
            del self._sessions[state]
            del self._timeouts[state]

    async def health_check(self) -> bool:
        """Always healthy for in-memory storage."""
        return True
