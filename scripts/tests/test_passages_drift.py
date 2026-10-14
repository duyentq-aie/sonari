"""Guard: the content service filters passages with constants the tools define, and cannot import
the tools (ADR-0010), so both copies are compared here. The sentence marks need no such check:
tools/speaking_items/classes.py computes them with pick.practicable itself."""

from sonari_core.content.passages import DEFAULT_RULE, USABLE_TYPES
from voa_corpus import classify, classify_report


def test_the_listed_types_are_the_classifier_s_usable_types() -> None:
    assert USABLE_TYPES == classify.USABLE_TYPES


def test_the_service_s_safety_rule_is_one_the_classes_file_carries() -> None:
    assert DEFAULT_RULE in classify_report.RULES
    assert classify_report.RULES[DEFAULT_RULE] == classify.BODY_HITS
