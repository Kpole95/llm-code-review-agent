"""Matching logic and precision/recall/F1 computation for the evaluation harness."""
from dataclasses import dataclass


@dataclass
class MatchResult:
    true_positives: int
    false_positives: int
    false_negatives: int

    @property
    def precision(self) -> float:
        denom = self.true_positives + self.false_positives
        return self.true_positives / denom if denom else 1.0

    @property
    def recall(self) -> float:
        denom = self.true_positives + self.false_negatives
        return self.true_positives / denom if denom else 1.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0


def _category_matches(predicted: str, expected: str) -> bool:
    """Exact match, or one category string is a substring of the other."""
    predicted, expected = predicted.lower(), expected.lower()
    if predicted == expected:
        return True
    return predicted in expected or expected in predicted


def match_findings(
    predicted: list[dict],
    expected: list[dict],
    line_tolerance: int = 2,
) -> MatchResult:
    """
    For each predicted finding, look for an unmatched expected finding within
    line_tolerance whose category matches. A match is a true positive and
    claims that expected finding. Anything predicted but unmatched is a false
    positive; anything expected but never claimed is a false negative.
    """
    matched_expected_indices = set()
    true_positives = 0

    for pred in predicted:
        found_match = False

        for i, exp in enumerate(expected):
            if i in matched_expected_indices:
                continue

            lo, hi = exp["line_range"]
            line_ok = (lo - line_tolerance) <= pred["line"] <= (hi + line_tolerance)

            if line_ok and _category_matches(pred["category"], exp["category"]):
                matched_expected_indices.add(i)
                found_match = True
                break

        if found_match:
            true_positives += 1

    false_positives = len(predicted) - true_positives
    false_negatives = len(expected) - len(matched_expected_indices)

    return MatchResult(
        true_positives=true_positives,
        false_positives=false_positives,
        false_negatives=false_negatives,
    )
