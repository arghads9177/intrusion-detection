"""Maps COCO class names to THREAT / NON_THREAT / IGNORE categories.

Only 'person' is alert-eligible.  All animals in the COCO taxonomy that
appear in perimeter-camera scenarios are NON_THREAT so they get suppressed
with reason='animal'.  Everything else (vehicles, objects) is IGNORE.
"""

from enum import Enum

# Complete COCO animal classes that could trigger false positives
_NON_THREAT_CLASSES: frozenset[str] = frozenset(
    [
        "bird",
        "cat",
        "dog",
        "horse",
        "sheep",
        "cow",
        "elephant",
        "bear",
        "zebra",
        "giraffe",
    ]
)

_THREAT_CLASSES: frozenset[str] = frozenset(["person"])


class ThreatLevel(str, Enum):
    THREAT = "threat"
    NON_THREAT = "non_threat"
    IGNORE = "ignore"


def classify(class_name: str) -> ThreatLevel:
    """Return the threat level for a YOLO class name."""
    if class_name in _THREAT_CLASSES:
        return ThreatLevel.THREAT
    if class_name in _NON_THREAT_CLASSES:
        return ThreatLevel.NON_THREAT
    return ThreatLevel.IGNORE


def is_alert_eligible(class_name: str) -> bool:
    return classify(class_name) == ThreatLevel.THREAT
