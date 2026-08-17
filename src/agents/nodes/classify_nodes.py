"""LangGraph nodes for waste classification."""

from __future__ import annotations

import json
import logging

from src.agents.state import ClassifyState
from src.services import safety
from src.services.vision import VisionProviderError, get_vision_model

logger = logging.getLogger(__name__)

CLASSIFY_PROMPT = """You are a waste-sorting classifier for a smart recycling bin.

Identify the single most prominent waste item in the image.

Reply with ONLY a JSON object, no prose and no code fences:
{"label": "<one of: plastic, paper, metal, glass, organic, battery, \
chemical, medical, sharps, e-waste, paint, aerosol, other>", \
"confidence": <number between 0 and 1>}

If the image is unclear, empty, or you cannot identify any waste item, reply \
with {"label": "", "confidence": 0.0}. Do not guess."""


def _parse_model_reply(text: str) -> tuple[str, float]:
    """Extract label and confidence from the model's reply.

    An unparseable reply yields an empty label, which the safety layer turns
    into ``refused``. It is never coerced into a plausible-looking class.
    """
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        # Drop a leading language tag such as ```json
        if "\n" in cleaned:
            cleaned = cleaned.split("\n", 1)[1]

    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1:
        return "", 0.0

    try:
        payload = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return "", 0.0

    label = str(payload.get("label", "") or "")
    try:
        confidence = float(payload.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0

    return label, max(0.0, min(1.0, confidence))


async def vision_node(state: ClassifyState) -> dict:
    """Call the routed Vision model with the already-preprocessed image."""
    image_b64 = state.get("image_b64", "")
    if not image_b64:
        return {"error": "No image supplied"}

    try:
        model = get_vision_model()
    except VisionProviderError as exc:
        logger.error("Vision provider unavailable: %s", exc)
        return {"error": str(exc)}

    message = {
        "role": "user",
        "content": [
            {"type": "text", "text": CLASSIFY_PROMPT},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
            },
        ],
    }

    try:
        response = await model.ainvoke([message])
    except Exception as exc:  # noqa: BLE001 - provider SDKs raise many types
        logger.exception("Vision call failed")
        return {"error": f"Vision call failed: {exc}"}

    text = str(response.content)
    label, confidence = _parse_model_reply(text)
    if not label:
        # An empty label becomes `refused` downstream, and the two reasons for it
        # — the model declining to guess, versus a reply we could not parse —
        # are indistinguishable without seeing what actually came back.
        logger.warning("Vision returned no label; raw reply was: %r", text[:300])
    return {"label": label, "confidence": confidence}


async def safety_node(state: ClassifyState) -> dict:
    """Apply safety/HITL rules. The only place an outcome is finalised."""
    if state.get("error"):
        return {"outcome": safety.errored(str(state["error"]))}

    return {
        "outcome": safety.evaluate(
            label=state.get("label", ""),
            confidence=float(state.get("confidence", 0.0)),
        )
    }
