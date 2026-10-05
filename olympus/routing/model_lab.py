"""Empirical Model Lab for OLYMPUS.

Records model+provider evidence by benchmark category and produces confidence-
adjusted routing scores. Benchmarks are expected to run only in disposable
workspaces; this module never mutates project files itself.
"""
from dataclasses import dataclass, field
from enum import Enum
from math import sqrt
from typing import Dict, Iterable, Optional, Tuple


class BenchmarkCategory(str, Enum):
    ACTION_PROTOCOL = "action_protocol"
    REPO_DISCOVERY = "repo_discovery"
    CODE_GENERATION = "code_generation"
    EXISTING_EDIT = "existing_edit"
    TEST_REPAIR = "test_repair"
    REASONING = "reasoning"
    LONG_HORIZON = "long_horizon"


@dataclass(frozen=True)
class RouteKey:
    provider: str
    model: str


@dataclass
class RouteMetrics:
    attempts: int = 0
    successes: int = 0
    timeouts: int = 0
    compliant_actions: int = 0
    repair_attempts: int = 0
    repair_successes: int = 0
    latencies_ms: list[int] = field(default_factory=list)

    def record(self, *, success: bool, latency_ms: int = 0, timeout: bool = False,
               action_compliant: Optional[bool] = None,
               repair_success: Optional[bool] = None) -> None:
        self.attempts += 1
        self.successes += int(bool(success))
        self.timeouts += int(bool(timeout))
        if action_compliant is True:
            self.compliant_actions += 1
        if repair_success is not None:
            self.repair_attempts += 1
            self.repair_successes += int(bool(repair_success))
        if latency_ms > 0:
            self.latencies_ms.append(int(latency_ms))

    @property
    def success_rate(self) -> float:
        return self.successes / self.attempts if self.attempts else 0.0

    @property
    def timeout_rate(self) -> float:
        return self.timeouts / self.attempts if self.attempts else 0.0

    @property
    def action_compliance(self) -> float:
        return self.compliant_actions / self.attempts if self.attempts else 0.0

    @property
    def repair_success(self) -> float:
        return self.repair_successes / self.repair_attempts if self.repair_attempts else 0.0

    @property
    def avg_latency_ms(self) -> float:
        return sum(self.latencies_ms) / len(self.latencies_ms) if self.latencies_ms else 0.0

    @property
    def p95_latency_ms(self) -> float:
        if not self.latencies_ms:
            return 0.0
        values = sorted(self.latencies_ms)
        index = max(0, min(len(values) - 1, int(0.95 * len(values) + 0.999999) - 1))
        return float(values[index])

    @property
    def confidence(self) -> float:
        """Sample confidence grows conservatively; 1/1 never equals mature evidence."""
        return min(1.0, sqrt(self.attempts / 25.0)) if self.attempts else 0.0


class ModelLab:
    def __init__(self) -> None:
        self._metrics: Dict[Tuple[BenchmarkCategory, RouteKey], RouteMetrics] = {}

    def metrics(self, category: BenchmarkCategory, provider: str, model: str) -> RouteMetrics:
        key = (BenchmarkCategory(category), RouteKey(provider, model))
        return self._metrics.setdefault(key, RouteMetrics())

    def record(self, category: BenchmarkCategory, provider: str, model: str, **kwargs) -> RouteMetrics:
        row = self.metrics(category, provider, model)
        row.record(**kwargs)
        return row

    def observed_score(self, category: BenchmarkCategory, provider: str, model: str) -> float:
        row = self.metrics(category, provider, model)
        if not row.attempts:
            return 0.5
        raw = (
            0.50 * row.success_rate
            + 0.20 * row.action_compliance
            + 0.15 * row.repair_success
            + 0.15 * (1.0 - row.timeout_rate)
        )
        # Shrink sparse evidence toward neutral 0.5.
        return 0.5 * (1.0 - row.confidence) + raw * row.confidence

    def routing_score(self, category: BenchmarkCategory, provider: str, model: str, *,
                      capability_score: float, health_score: float = 1.0,
                      cost_score: float = 1.0) -> float:
        observed = self.observed_score(category, provider, model)
        score = (
            0.40 * max(0.0, min(1.0, capability_score))
            + 0.30 * observed
            + 0.20 * max(0.0, min(1.0, health_score))
            + 0.10 * max(0.0, min(1.0, cost_score))
        )
        return max(0.0, min(1.0, score))

    def rank(self, category: BenchmarkCategory, routes: Iterable[dict]) -> tuple[dict, ...]:
        ranked = []
        for route in routes:
            item = dict(route)
            item["score"] = self.routing_score(
                category, item["provider"], item["model"],
                capability_score=float(item.get("capability_score", 0.5)),
                health_score=float(item.get("health_score", 1.0)),
                cost_score=float(item.get("cost_score", 1.0)),
            )
            metrics = self.metrics(category, item["provider"], item["model"])
            item["sample_size"] = metrics.attempts
            item["confidence"] = metrics.confidence
            ranked.append(item)
        return tuple(sorted(ranked, key=lambda row: (-row["score"], -row["sample_size"], row["provider"], row["model"])))
