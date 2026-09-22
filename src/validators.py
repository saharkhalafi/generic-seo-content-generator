from __future__ import annotations

from src.schemas import HeadingPlan, HeadingValidationResult, UserInput
from src.scoring import (
    evaluate,
    extract_introduction,
    heading_duplicates,
    keyword_density,
    validate_heading_plan,
    validate_metadata,
)

__all__ = [
    "evaluate",
    "extract_introduction",
    "heading_duplicates",
    "keyword_density",
    "validate_heading_plan",
    "validate_headings_locally",
    "validate_metadata",
]


def validate_headings_locally(architecture: HeadingPlan, user_input: UserInput) -> HeadingValidationResult:
    checks = validate_heading_plan(architecture, user_input)
    fails = [item for item in checks if item.status == "FAIL"]
    return HeadingValidationResult(
        passed=not fails,
        summary="ساختار هدینگ قابل قبول است." if not fails else "ساختار هدینگ نیاز به اصلاح دارد.",
        checks=checks,
        failed_checks=[item.code for item in fails],
        overall_score=0 if fails else 100,
    )
