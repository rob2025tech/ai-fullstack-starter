from datetime import timedelta

from app.learning.scheduler import review_interval


def test_low_mastery_reviews_in_one_day():
    assert review_interval(0.20) == timedelta(days=1)


def test_medium_low_mastery_reviews_in_three_days():
    assert review_interval(0.40) == timedelta(days=3)


def test_upper_medium_mastery_reviews_in_seven_days():
    assert review_interval(0.70) == timedelta(days=7)


def test_high_mastery_reviews_in_fourteen_days():
    assert review_interval(0.90) == timedelta(days=14)


def test_boundary_below_point_seven_is_three_days():
    assert review_interval(0.69) == timedelta(days=3)


def test_boundary_below_point_nine_is_seven_days():
    assert review_interval(0.89) == timedelta(days=7)
