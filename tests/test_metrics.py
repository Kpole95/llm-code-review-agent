from src.eval.metrics import match_findings


def test_perfect_match():
    predicted = [{"line": 8, "category": "sql_injection"}]
    expected = [{"line_range": [8, 8], "category": "sql_injection", "severity": "high"}]

    result = match_findings(predicted, expected)
    assert result.true_positives == 1
    assert result.false_positives == 0
    assert result.false_negatives == 0
    assert result.precision == 1.0
    assert result.recall == 1.0
    assert result.f1 == 1.0


def test_extra_finding_hurts_precision_not_recall():
    # This is the worked example above.
    predicted = [
        {"line": 8, "category": "sql_injection"},
        {"line": 6, "category": "resource_leak"},
    ]
    expected = [{"line_range": [8, 8], "category": "sql_injection", "severity": "high"}]

    result = match_findings(predicted, expected)
    assert result.true_positives == 1
    assert result.false_positives == 1
    assert result.false_negatives == 0
    assert result.precision == 0.5
    assert result.recall == 1.0


def test_missed_finding_hurts_recall_not_precision():
    predicted = []  # pipeline found nothing
    expected = [{"line_range": [8, 8], "category": "sql_injection", "severity": "high"}]

    result = match_findings(predicted, expected)
    assert result.true_positives == 0
    assert result.false_negatives == 1
    assert result.recall == 0.0
    assert result.precision == 1.0  # reported nothing, so no FALSE positives


def test_clean_file_no_predictions_no_expectations():
    result = match_findings([], [])
    assert result.precision == 1.0
    assert result.recall == 1.0
    assert result.f1 == 1.0


def test_line_tolerance():
    # predicted is 2 lines off from expected — should still match.
    predicted = [{"line": 10, "category": "sql_injection"}]
    expected = [{"line_range": [8, 8], "category": "sql_injection", "severity": "high"}]

    result = match_findings(predicted, expected, line_tolerance=2)
    assert result.true_positives == 1

    # But 3 lines off, with tolerance=2, should NOT match.
    result_strict = match_findings(predicted, expected, line_tolerance=1)
    assert result_strict.true_positives == 0