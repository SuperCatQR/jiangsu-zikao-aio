"""Unit tests for lifecycle + completeness status machine."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

from lib.course_status import (
    map_legacy_status_field,
    maturity_level,
    parse_course_status,
    CourseStatus,
)


def test_map_legacy_status():
    assert map_legacy_status_field(None) == "draft"
    assert map_legacy_status_field("draft") == "draft"
    assert map_legacy_status_field("yellow") == "machine_ready"
    assert map_legacy_status_field("") == "draft"


def test_parse_prefers_lifecycle():
    st = parse_course_status({"lifecycle": "in_review", "status": "yellow"}, {"资料状态": "metadata-only"})
    assert st.lifecycle == "in_review"
    assert st.completeness == "metadata-only"


def test_parse_legacy_status_as_lifecycle():
    st = parse_course_status({"status": "yellow"}, {"资料状态": "complete"})
    assert st.lifecycle == "machine_ready"
    assert st.completeness == "complete"


def test_publishable_flag():
    assert CourseStatus("publishable", "complete").is_publishable()
    assert not CourseStatus("machine_ready", "complete").is_publishable()


def test_maturity_levels():
    assert maturity_level(CourseStatus("draft", "missing-source")) == "red"
    assert maturity_level(CourseStatus("machine_ready", "metadata-only")) == "yellow"
    assert maturity_level(CourseStatus("publishable", "complete"), thin=False) == "green"
    assert maturity_level(CourseStatus("publishable", "complete"), thin=True) == "yellow"
