"""
Cost Optimization Service for OpenAI API usage.
Implements intelligent caching, batch processing, and cost monitoring.
"""

import hashlib
import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.audit import audit_logger_instance

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """Cache entry for NLP results."""

    input_hash: str
    result: Dict[str, Any]
    timestamp: datetime
    confidence: float
    usage_count: int = 1
    last_used: datetime = None

    def __post_init__(self):
        if self.last_used is None:
            self.last_used = self.timestamp

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "input_hash": self.input_hash,
            "result": self.result,
            "timestamp": self.timestamp.isoformat(),
            "confidence": self.confidence,
            "usage_count": self.usage_count,
            "last_used": self.last_used.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CacheEntry":
        """Create from dictionary."""
        return cls(
            input_hash=data["input_hash"],
            result=data["result"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            confidence=data["confidence"],
            usage_count=data["usage_count"],
            last_used=datetime.fromisoformat(data["last_used"]),
        )


class CostOptimizer:
    """
    Cost optimization service for OpenAI API usage.

    Features:
    - Intelligent caching for repeated extraction patterns
    - Batch processing for multiple entities
    - Prompt engineering optimization
    - Token usage monitoring and alerts
    - Cache hit rate tracking
    """

    def __init__(self, cache_file: str = "nlp_cache.json"):
        """Initialize cost optimizer."""
        self.cache_file = Path(cache_file)
        self.cache: Dict[str, CacheEntry] = {}
        self.max_cache_size = 1000
        self.cache_ttl_hours = 24
        self.similarity_threshold = 0.85

        # Cost tracking
        self.cost_stats = {
            "total_requests": 0,
            "cached_requests": 0,
            "cache_hit_rate": 0.0,
            "tokens_saved": 0,
            "cost_saved_dollars": 0.0,
            "monthly_budget": 197.0,
            "alert_threshold": 0.8,
        }

        self._load_cache()

    def _load_cache(self):
        """Load cache from file."""
        try:
            if self.cache_file.exists():
                with open(self.cache_file, "r") as f:
                    cache_data = json.load(f)

                for entry_data in cache_data.get("entries", []):
                    try:
                        entry = CacheEntry.from_dict(entry_data)
                        self.cache[entry.input_hash] = entry
                    except Exception as e:
                        logger.warning(f"Failed to load cache entry: {e}")

                self.cost_stats.update(cache_data.get("cost_stats", {}))
                logger.info(f"Loaded {len(self.cache)} cache entries")

                # Clean expired entries
                self._cleanup_expired_entries()

        except Exception as e:
            logger.error(f"Failed to load cache: {e}")

    def _save_cache(self):
        """Save cache to file."""
        try:
            cache_data = {
                "entries": [entry.to_dict() for entry in self.cache.values()],
                "cost_stats": self.cost_stats,
                "last_updated": datetime.utcnow().isoformat(),
            }

            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_file, "w") as f:
                json.dump(cache_data, f, indent=2)

        except Exception as e:
            logger.error(f"Failed to save cache: {e}")

    def _cleanup_expired_entries(self):
        """Remove expired cache entries."""
        current_time = datetime.utcnow()
        expired_hashes = []

        for input_hash, entry in self.cache.items():
            age_hours = (current_time - entry.timestamp).total_seconds() / 3600
            if age_hours > self.cache_ttl_hours:
                expired_hashes.append(input_hash)

        for input_hash in expired_hashes:
            del self.cache[input_hash]

        if expired_hashes:
            logger.info(f"Cleaned up {len(expired_hashes)} expired cache entries")

    def _generate_input_hash(self, text: str, context_key: str = "") -> str:
        """Generate hash for input text and context."""
        # Normalize text for consistent hashing
        normalized_text = text.lower().strip()
        combined_input = f"{normalized_text}|{context_key}"
        return hashlib.sha256(combined_input.encode()).hexdigest()[:16]

    def _calculate_text_similarity(self, text1: str, text2: str) -> float:
        """Calculate simple text similarity score."""
        # Simple word-based similarity - in production, use proper similarity metrics
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())

        if not words1 and not words2:
            return 1.0
        if not words1 or not words2:
            return 0.0

        intersection = words1.intersection(words2)
        union = words1.union(words2)

        return len(intersection) / len(union) if union else 0.0

    def check_cache(self, text: str, context_key: str = "") -> Optional[Dict[str, Any]]:
        """
        Check cache for similar extraction results.

        Args:
            text: Input text to check
            context_key: Context identifier for cache lookup

        Returns:
            Cached result if found, None otherwise
        """
        try:
            self.cost_stats["total_requests"] += 1

            input_hash = self._generate_input_hash(text, context_key)

            # Exact match
            if input_hash in self.cache:
                entry = self.cache[input_hash]
                entry.usage_count += 1
                entry.last_used = datetime.utcnow()

                self.cost_stats["cached_requests"] += 1
                self._update_cache_hit_rate()

                audit_logger_instance.log_system_event(
                    action="NLP_CACHE_HIT",
                    result="SUCCESS",
                    additional_data={
                        "input_hash": input_hash,
                        "usage_count": entry.usage_count,
                        "confidence": entry.confidence,
                    },
                )

                logger.info(f"Cache hit for input hash {input_hash}")
                return entry.result

            # Similarity-based matching for high-confidence entries
            normalized_text = text.lower().strip()
            for cached_hash, entry in self.cache.items():
                if entry.confidence >= 0.8:  # Only use high-confidence cached results
                    # Extract original text from cached result for similarity check
                    cached_text = entry.result.get("input_text", "")
                    similarity = self._calculate_text_similarity(
                        normalized_text, cached_text
                    )

                    if similarity >= self.similarity_threshold:
                        entry.usage_count += 1
                        entry.last_used = datetime.utcnow()

                        self.cost_stats["cached_requests"] += 1
                        self._update_cache_hit_rate()

                        audit_logger_instance.log_system_event(
                            action="NLP_CACHE_SIMILARITY_HIT",
                            result="SUCCESS",
                            additional_data={
                                "input_hash": input_hash,
                                "cached_hash": cached_hash,
                                "similarity": similarity,
                                "usage_count": entry.usage_count,
                            },
                        )

                        logger.info(
                            f"Similarity cache hit (score: {similarity:.2f}) for {input_hash}"
                        )
                        return entry.result

            return None

        except Exception as e:
            logger.error(f"Cache check failed: {e}")
            return None

    def store_result(self, text: str, result: Dict[str, Any], context_key: str = ""):
        """
        Store extraction result in cache.

        Args:
            text: Input text
            result: Extraction result to cache
            context_key: Context identifier
        """
        try:
            input_hash = self._generate_input_hash(text, context_key)
            confidence = result.get("overall_confidence", 0.0)

            # Only cache high-confidence results
            if confidence >= 0.7:
                entry = CacheEntry(
                    input_hash=input_hash,
                    result=result,
                    timestamp=datetime.utcnow(),
                    confidence=confidence,
                )

                self.cache[input_hash] = entry

                # Manage cache size
                if len(self.cache) > self.max_cache_size:
                    self._evict_cache_entries()

                audit_logger_instance.log_system_event(
                    action="NLP_CACHE_STORE",
                    result="SUCCESS",
                    additional_data={
                        "input_hash": input_hash,
                        "confidence": confidence,
                        "cache_size": len(self.cache),
                    },
                )

                logger.info(
                    f"Stored result in cache: {input_hash} (confidence: {confidence:.2f})"
                )

        except Exception as e:
            logger.error(f"Failed to store cache result: {e}")

    def _evict_cache_entries(self):
        """Remove least-used cache entries when cache is full."""
        # Sort by usage count and last used time
        sorted_entries = sorted(
            self.cache.items(), key=lambda x: (x[1].usage_count, x[1].last_used)
        )

        # Remove oldest 10% of entries
        entries_to_remove = int(self.max_cache_size * 0.1)
        for i in range(entries_to_remove):
            if i < len(sorted_entries):
                input_hash = sorted_entries[i][0]
                del self.cache[input_hash]

        logger.info(f"Evicted {entries_to_remove} cache entries")

    def _update_cache_hit_rate(self):
        """Update cache hit rate statistics."""
        if self.cost_stats["total_requests"] > 0:
            self.cost_stats["cache_hit_rate"] = (
                self.cost_stats["cached_requests"] / self.cost_stats["total_requests"]
            )

    def optimize_prompt(self, prompt: str, entity_types: List[str] = None) -> str:
        """
        Optimize prompt for token efficiency.

        Args:
            prompt: Original prompt
            entity_types: Specific entity types to focus on

        Returns:
            Optimized prompt
        """
        # Basic prompt optimization strategies
        optimizations = [
            # Remove unnecessary words
            ("please", ""),
            ("could you", ""),
            ("I would like", ""),
            ("if possible", ""),
            # Use abbreviations for common medical terms
            ("appointment", "appt"),
            ("prescription", "Rx"),
            ("examination", "exam"),
            # Compress instructions
            ("Extract the following information:", "Extract:"),
            ("Please identify:", "Find:"),
            ("Determine the", "Get"),
        ]

        optimized_prompt = prompt
        for old, new in optimizations:
            optimized_prompt = optimized_prompt.replace(old, new)

        # Focus on specific entity types if provided
        if entity_types:
            entity_focus = ", ".join(entity_types)
            optimized_prompt += f" Focus on: {entity_focus}"

        return optimized_prompt.strip()

    def batch_process_entities(self, inputs: List[str]) -> List[str]:
        """
        Optimize multiple inputs for batch processing.

        Args:
            inputs: List of input texts

        Returns:
            List of optimized prompts for batch processing
        """
        if len(inputs) <= 1:
            return inputs

        # Group similar inputs for more efficient processing
        grouped_inputs = []
        current_group = []

        for text in inputs:
            if not current_group:
                current_group.append(text)
            else:
                # Check similarity with current group
                similarity = max(
                    self._calculate_text_similarity(text, existing)
                    for existing in current_group
                )

                if similarity >= 0.7 and len(current_group) < 3:
                    current_group.append(text)
                else:
                    grouped_inputs.append(current_group)
                    current_group = [text]

        if current_group:
            grouped_inputs.append(current_group)

        # Create batch prompts
        batch_prompts = []
        for group in grouped_inputs:
            if len(group) == 1:
                batch_prompts.append(group[0])
            else:
                combined_prompt = f"Extract entities from these {len(group)} inputs:\n"
                for i, text in enumerate(group, 1):
                    combined_prompt += f"{i}. {text}\n"
                batch_prompts.append(combined_prompt)

        return batch_prompts

    def track_cost_savings(self, tokens_saved: int, requests_cached: int):
        """
        Track cost savings from optimization.

        Args:
            tokens_saved: Number of tokens saved
            requests_cached: Number of requests served from cache
        """
        # GPT-3.5-turbo pricing: ~$0.0015 per 1K tokens
        cost_saved = (tokens_saved / 1000) * 0.0015

        self.cost_stats["tokens_saved"] += tokens_saved
        self.cost_stats["cost_saved_dollars"] += cost_saved

        audit_logger_instance.log_system_event(
            action="COST_OPTIMIZATION_SAVINGS",
            result="SUCCESS",
            additional_data={
                "tokens_saved": tokens_saved,
                "requests_cached": requests_cached,
                "cost_saved_dollars": cost_saved,
                "total_cost_saved": self.cost_stats["cost_saved_dollars"],
            },
        )

    def get_optimization_stats(self) -> Dict[str, Any]:
        """Get cost optimization statistics."""
        return {
            **self.cost_stats,
            "cache_size": len(self.cache),
            "cache_efficiency": self.cost_stats["cache_hit_rate"] * 100,
            "average_confidence": (
                sum(entry.confidence for entry in self.cache.values()) / len(self.cache)
                if self.cache
                else 0.0
            ),
            "total_usage_count": sum(
                entry.usage_count for entry in self.cache.values()
            ),
        }

    def check_budget_alert(self, current_cost: float) -> Optional[Dict[str, Any]]:
        """
        Check if budget alert should be triggered.

        Args:
            current_cost: Current monthly cost in dollars

        Returns:
            Alert information if threshold exceeded
        """
        budget_used_percent = current_cost / self.cost_stats["monthly_budget"]

        if budget_used_percent >= self.cost_stats["alert_threshold"]:
            return {
                "alert_type": "budget_threshold",
                "current_cost": current_cost,
                "budget": self.cost_stats["monthly_budget"],
                "percent_used": budget_used_percent * 100,
                "threshold": self.cost_stats["alert_threshold"] * 100,
                "savings_to_date": self.cost_stats["cost_saved_dollars"],
                "recommendation": "Consider increasing cache usage or optimizing prompts",
            }

        return None

    def cleanup_and_save(self):
        """Cleanup expired entries and save cache."""
        self._cleanup_expired_entries()
        self._save_cache()


# Global cost optimizer instance
cost_optimizer = CostOptimizer()
