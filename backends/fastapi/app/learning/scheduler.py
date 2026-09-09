from datetime import timedelta


def review_interval(mastery: float) -> timedelta:
    """Return the next review interval using a deterministic demo heuristic.

    This is a demo heuristic, not a scientifically validated schedule.
    """
    if mastery < 0.40:
        return timedelta(days=1)

    if mastery < 0.70:
        return timedelta(days=3)

    if mastery < 0.90:
        return timedelta(days=7)

    return timedelta(days=14)
