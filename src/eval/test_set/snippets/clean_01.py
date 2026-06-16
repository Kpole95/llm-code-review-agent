def average(numbers: list[float]) -> float:
    """Return the arithmetic mean of a non-empty list of numbers."""
    if not numbers:
        raise ValueError("numbers must not be empty")
    return sum(numbers) / len(numbers)
