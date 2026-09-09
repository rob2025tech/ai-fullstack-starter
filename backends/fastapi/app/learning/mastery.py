def update_mastery(
    current: float,
    *,
    is_correct: bool,
    had_misconception: bool,
) -> float:
    """Update estimated mastery using a deterministic demo heuristic.

    This is a demo heuristic, not a scientifically validated measurement.
    """
    if is_correct:
        delta = 0.30 if had_misconception else 0.20
    else:
        delta = -0.05

    return max(0.0, min(1.0, current + delta))
