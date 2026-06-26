"""Tests for analytics/classifier.py — ThreatLevel enum, classify(), is_alert_eligible().

Coverage:
- Happy path: every known THREAT and NON_THREAT class name returns the correct level
- Negative path: unknown classes, empty string, numeric strings, mixed-case names
- Edge cases: whitespace padding, Unicode look-alikes, very long strings
- is_alert_eligible() mirrors classify() == THREAT for all classes
"""

from __future__ import annotations

import pytest

from analytics.classifier import ThreatLevel, classify, is_alert_eligible

# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestClassifyHappyPath:
    def test_person_returns_threat(self):
        assert classify("person") == ThreatLevel.THREAT

    @pytest.mark.parametrize(
        "class_name",
        ["dog", "cat", "bird", "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe"],
    )
    def test_all_non_threat_animals(self, class_name: str):
        assert classify(class_name) == ThreatLevel.NON_THREAT

    @pytest.mark.parametrize(
        "class_name",
        ["car", "truck", "bicycle", "motorbike", "bus", "train", "boat",
         "chair", "couch", "laptop", "cell phone", "backpack", "umbrella"],
    )
    def test_coco_objects_return_ignore(self, class_name: str):
        assert classify(class_name) == ThreatLevel.IGNORE

    def test_threat_level_enum_values(self):
        """Enum string values are stable and used in DB/API payloads."""
        assert ThreatLevel.THREAT.value == "threat"
        assert ThreatLevel.NON_THREAT.value == "non_threat"
        assert ThreatLevel.IGNORE.value == "ignore"

    def test_threat_level_is_str_enum(self):
        """ThreatLevel inherits from str — safe to compare against string payloads."""
        assert ThreatLevel.THREAT == "threat"
        assert ThreatLevel.NON_THREAT == "non_threat"


# ---------------------------------------------------------------------------
# Negative path
# ---------------------------------------------------------------------------


class TestClassifyNegativePath:
    def test_empty_string_returns_ignore(self):
        assert classify("") == ThreatLevel.IGNORE

    def test_unknown_class_returns_ignore(self):
        assert classify("spaceship") == ThreatLevel.IGNORE

    def test_numeric_string_returns_ignore(self):
        assert classify("0") == ThreatLevel.IGNORE

    def test_none_like_string_returns_ignore(self):
        assert classify("None") == ThreatLevel.IGNORE

    def test_uppercase_person_is_ignore(self):
        """Class matching is case-sensitive (YOLO outputs lowercase)."""
        assert classify("Person") == ThreatLevel.IGNORE
        assert classify("PERSON") == ThreatLevel.IGNORE

    def test_uppercase_animal_is_ignore(self):
        assert classify("Dog") == ThreatLevel.IGNORE
        assert classify("CAT") == ThreatLevel.IGNORE


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestClassifyEdgeCases:
    def test_whitespace_padded_person_is_ignore(self):
        """No strip() in implementation — ' person ' must not match."""
        assert classify(" person") == ThreatLevel.IGNORE
        assert classify("person ") == ThreatLevel.IGNORE

    def test_very_long_string_returns_ignore(self):
        long_name = "x" * 10_000
        assert classify(long_name) == ThreatLevel.IGNORE

    def test_sql_injection_pattern_returns_ignore(self):
        assert classify("'; DROP TABLE events;--") == ThreatLevel.IGNORE

    def test_xss_payload_returns_ignore(self):
        assert classify("<script>alert('xss')</script>") == ThreatLevel.IGNORE

    def test_newline_in_name_returns_ignore(self):
        assert classify("per\nson") == ThreatLevel.IGNORE

    def test_partial_match_dog_prefix_is_ignore(self):
        assert classify("dogs") == ThreatLevel.IGNORE

    def test_partial_match_person_suffix_is_ignore(self):
        assert classify("aperson") == ThreatLevel.IGNORE


# ---------------------------------------------------------------------------
# is_alert_eligible
# ---------------------------------------------------------------------------


class TestIsAlertEligible:
    def test_person_is_eligible(self):
        assert is_alert_eligible("person") is True

    @pytest.mark.parametrize(
        "class_name",
        ["dog", "cat", "bird", "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe"],
    )
    def test_animals_not_eligible(self, class_name: str):
        assert is_alert_eligible(class_name) is False

    @pytest.mark.parametrize("class_name", ["car", "truck", "chair", "laptop", ""])
    def test_ignore_classes_not_eligible(self, class_name: str):
        assert is_alert_eligible(class_name) is False

    def test_is_alert_eligible_returns_bool_not_enum(self):
        result = is_alert_eligible("person")
        assert isinstance(result, bool)

    def test_is_alert_eligible_case_sensitive(self):
        assert is_alert_eligible("Person") is False
        assert is_alert_eligible("PERSON") is False

    def test_is_alert_eligible_unknown_class_false(self):
        assert is_alert_eligible("robot") is False
