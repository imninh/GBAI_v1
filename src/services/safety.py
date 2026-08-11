"""Safety and HITL rules applied to every classification.

Kept separate from the model call so the rules are testable without a provider,
and so the same rules apply no matter which surface produced the image — PWA or
IoT device. Spec §11 and §26: an uncertain result is never forced into a
confident class.
"""

from __future__ import annotations

from src.config import get_settings
from src.models.schemas import ClassifyOutcome


def _hazard_labels() -> set[str]:
    settings = get_settings()
    return {
        label.strip().lower()
        for label in settings.hazard_labels.split(",")
        if label.strip()
    }


def evaluate(label: str, confidence: float) -> ClassifyOutcome:
    """Turn a raw model prediction into a safety-checked outcome.

    Order matters: hazard beats low confidence. A possible battery reported at
    40% confidence is a hazard warning, not a shrug — the cost of a false
    positive is a human glance, the cost of a false negative is a fire.
    """
    settings = get_settings()
    normalised = (label or "").strip().lower()

    if not normalised:
        return ClassifyOutcome(
            status="refused",
            label="",
            confidence=confidence,
            requires_review=True,
            message="Model returned no label",
        )

    if normalised in _hazard_labels():
        return ClassifyOutcome(
            status="hazard",
            label=normalised,
            confidence=confidence,
            requires_review=True,
            message="Hazardous material — do not deposit; awaiting human review",
        )

    if confidence < settings.low_confidence_threshold:
        return ClassifyOutcome(
            status="warning",
            label=normalised,
            confidence=confidence,
            # Flagged for a human rather than silently accepted.
            requires_review=True,
            message=(
                f"Low confidence ({confidence:.2f} < "
                f"{settings.low_confidence_threshold:.2f}); not treated as certain"
            ),
        )

    return ClassifyOutcome(
        status="ok",
        label=normalised,
        confidence=confidence,
        requires_review=False,
        message="Classified",
    )


def refused(reason: str) -> ClassifyOutcome:
    """The request was understood but the system declines to answer."""
    return ClassifyOutcome(
        status="refused",
        label="",
        confidence=0.0,
        requires_review=True,
        message=reason,
    )


def errored(reason: str) -> ClassifyOutcome:
    """Something broke. Never presented to the device as a classification."""
    return ClassifyOutcome(
        status="error",
        label="",
        confidence=0.0,
        requires_review=False,
        message=reason,
    )
