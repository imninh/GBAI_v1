"""Tests for safety / HITL rules (spec §11)."""

import pytest

from src.config import get_settings
from src.services import safety


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_confident_ordinary_waste_is_ok():
    outcome = safety.evaluate("plastic", 0.94)
    assert outcome.status == "ok"
    assert outcome.label == "plastic"
    assert outcome.requires_review is False


def test_low_confidence_becomes_warning_and_needs_review():
    outcome = safety.evaluate("plastic", 0.21)
    assert outcome.status == "warning"
    assert outcome.requires_review is True
    # The label is still reported, but the status makes the uncertainty explicit.
    assert outcome.confidence == pytest.approx(0.21)


def test_hazard_label_beats_low_confidence():
    """A possible battery at low confidence is a hazard, not a shrug."""
    outcome = safety.evaluate("battery", 0.35)
    assert outcome.status == "hazard"
    assert outcome.requires_review is True


@pytest.mark.parametrize("label", ["battery", "chemical", "medical", "sharps", "e-waste"])
def test_all_configured_hazard_labels(label):
    assert safety.evaluate(label, 0.99).status == "hazard"


def test_label_matching_is_case_insensitive():
    assert safety.evaluate("BATTERY", 0.9).status == "hazard"
    assert safety.evaluate("  Plastic  ", 0.9).label == "plastic"


@pytest.mark.parametrize("label", ["", "   ", None])
def test_empty_label_is_refused_not_guessed(label):
    outcome = safety.evaluate(label, 0.9)
    assert outcome.status == "refused"
    assert outcome.label == ""
    assert outcome.requires_review is True


def test_errored_never_looks_like_a_classification():
    outcome = safety.errored("provider exploded")
    assert outcome.status == "error"
    assert outcome.label == ""
    assert outcome.confidence == 0.0


def test_threshold_boundary_is_inclusive_on_ok_side(monkeypatch):
    monkeypatch.setenv("LOW_CONFIDENCE_THRESHOLD", "0.6")
    get_settings.cache_clear()
    assert safety.evaluate("paper", 0.6).status == "ok"
    assert safety.evaluate("paper", 0.599).status == "warning"
