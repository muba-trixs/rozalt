"""Configurable LLM provider for evidence-grounded synthesis (Anthropic Claude by default).

The model only sees the structured evidence package and must answer in the ``HypothesisReport``
schema. Output is then validated by ``validate_report``; invalid output is retried once with the
validation errors, after which the investigation falls back to the deterministic engine.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Protocol

from backend.app.config import Settings
from backend.services.hypothesis_generator import HypothesisReport

logger = logging.getLogger("demand_intel.llm")

SYSTEM_PROMPT = """You are an analytical assistant for enterprise demand planners investigating why recorded \
sales deviated from forecast for one SKU in one region.

You receive a JSON evidence package produced by deterministic statistical analysis. Work ONLY from it:
- Cite evidence exclusively by the evidence_id values provided. Never invent events, numbers or IDs.
- Each evidence item lists `targets`: the candidate events it supports or contradicts. Respect those roles.
- Distinguish forecast (planned), recorded sales (observed, bounded by inventory) and underlying demand \
(not observed). Never describe a fall in recorded sales as a fall in demand when stockouts are present.
- Use associative language ("consistent with", "associated with", "coincided with", "may have contributed"). \
Never claim causation or certainty (do not use: caused, proves, due to, because of, resulted in, led to, drove).
- Do not state confidence percentages or probabilities. Heuristic relevance scores are rankings, not probabilities.
- Evidence strength: STRONG only when timing, geography, mechanism and an independent statistical or \
inventory corroboration align with no material contradiction; MODERATE when the alignment is partial; WEAK when \
plausible but thinly supported. Rank hypotheses by evidence strength.
- If no candidate is adequately supported, return a single hypothesis with driver_type "none", strength \
INSUFFICIENT, claim_type "assumption", and the summary "Insufficient evidence to identify a likely driver."
- Use claim_type "hypothesis" for proposed drivers; never "fact".
- Explain contradicting evidence explicitly and keep alternative explanations when several remain plausible.
- Recommended actions must be concrete verification steps for a demand planner.
- driver_type must be one of the driver types present in the candidates, "inventory_constraint" when \
inventory evidence supports an unexplained supply constraint, or "none"."""


class LLMProvider(Protocol):
    name: str
    model: str

    def generate(self, package: dict, feedback: list[str] | None = None) -> "LLMResult": ...


@dataclass
class LLMResult:
    report: HypothesisReport | None
    notes: list[str] = field(default_factory=list)
    latency_ms: float = 0.0
    served_model: str | None = None


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, settings: Settings):
        import anthropic

        self._anthropic = anthropic
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key, max_retries=2, timeout=180.0)
        self.model = settings.llm_model
        self.effort = settings.llm_effort
        self.max_tokens = settings.llm_max_tokens

    def generate(self, package: dict, feedback: list[str] | None = None) -> LLMResult:
        a = self._anthropic
        content = "Evidence package:\n```json\n" + json.dumps(package, indent=1, default=str) + "\n```"
        if feedback:
            content += ("\n\nYour previous answer failed validation for these reasons. Return a corrected "
                        "report:\n- " + "\n- ".join(feedback))
        t0 = time.perf_counter()
        try:
            response = self.client.beta.messages.parse(
                model=self.model,
                max_tokens=self.max_tokens,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": content}],
                output_format=HypothesisReport,
                output_config={"effort": self.effort},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except a.AuthenticationError:
            return LLMResult(None, ["LLM authentication failed (check ANTHROPIC_API_KEY)"])
        except a.NotFoundError:
            return LLMResult(None, [f"LLM model '{self.model}' not found"])
        except a.BadRequestError as e:
            return LLMResult(None, [f"LLM request rejected: {e.message}"])
        except a.RateLimitError:
            return LLMResult(None, ["LLM rate limited"])
        except a.APIStatusError as e:
            return LLMResult(None, [f"LLM API error {e.status_code}: {e.message}"])
        except a.APIConnectionError:
            return LLMResult(None, ["LLM connection failed"])
        latency = (time.perf_counter() - t0) * 1000
        if response.stop_reason == "refusal":
            cat = getattr(response.stop_details, "category", None) if response.stop_details else None
            return LLMResult(None, [f"LLM declined the request (category: {cat})"], latency, response.model)
        if response.stop_reason == "max_tokens":
            return LLMResult(None, ["LLM output truncated at max_tokens"], latency, response.model)
        parsed = response.parsed_output
        if parsed is None:
            return LLMResult(None, ["LLM returned no parseable structured output"], latency, response.model)
        return LLMResult(parsed, [], latency, response.model)


def get_provider(settings: Settings) -> LLMProvider | None:
    if not settings.llm_available:
        return None
    try:
        return AnthropicProvider(settings)
    except Exception as exc:  # pragma: no cover - SDK import/config failure
        logger.warning("LLM provider unavailable: %s", exc)
        return None
