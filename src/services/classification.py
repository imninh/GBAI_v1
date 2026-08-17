"""Waste classification service.

The only entry point for turning an image into a classification. It accepts a
:class:`ProcessedImage` rather than raw bytes, which makes bypassing the privacy
pipeline a type error instead of a code-review question (spec §10, §26).
"""

from __future__ import annotations

import base64
import logging

from src.agents.classify_graph import classify_agent
from src.models.schemas import ClassifyOutcome
from src.services import safety
from src.services.image_privacy import ProcessedImage

logger = logging.getLogger(__name__)


async def classify_processed_image(
    image: ProcessedImage, source: str = "iot"
) -> ClassifyOutcome:
    """Classify an image that has already been through the privacy pipeline."""
    encoded = base64.b64encode(image.content).decode("ascii")

    try:
        result = await classify_agent.ainvoke(
            {
                "image_b64": encoded,
                "phash": image.phash,
                "source": source,
            }
        )
    except Exception as exc:  # noqa: BLE001 - graph/provider failures vary
        logger.exception("Classification graph failed")
        return safety.errored(f"Classification failed: {exc}")

    outcome = result.get("outcome")
    if outcome is None:
        # Should be unreachable — the safety node always sets it — but a missing
        # outcome must never read as success.
        logger.error("Classification graph returned no outcome")
        return safety.errored("Classifier produced no outcome")

    return outcome
