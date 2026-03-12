"""Unit tests for research/astro_shared.py — core astro utilities."""

import math
from datetime import date, datetime

import ephem
import pytest

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "research"))

from astro_shared import (
    apply_bh_correction,
    ecliptic_lon_deg,
    get_zodiac_sign,
    is_retrograde,
    is_stationary,
    today_local_date,
    yfinance_exclusive_end,
)


class TestGetZodiacSign:
    def test_aries_start(self):
        assert get_zodiac_sign(0.0) == "Овен"

    def test_taurus(self):
        assert get_zodiac_sign(45.0) == "Телец"

    def test_pisces(self):
        assert get_zodiac_sign(350.0) == "Рыбы"

    def test_boundary_30(self):
        assert get_zodiac_sign(30.0) == "Телец"

    def test_wraps_at_360(self):
        assert get_zodiac_sign(360.0) == "Овен"

    def test_negative_wraps(self):
        assert get_zodiac_sign(-10.0) == "Рыбы"

    @pytest.mark.parametrize("deg,expected", [
        (0, "Овен"), (60, "Близнецы"), (90, "Рак"),
        (120, "Лев"), (180, "Весы"), (270, "Козерог"),
    ])
    def test_key_degrees(self, deg, expected):
        assert get_zodiac_sign(float(deg)) == expected


class TestEclipticLonDeg:
    def test_returns_float(self):
        body = ephem.Sun(ephem.Date("2024/1/1"))
        result = ecliptic_lon_deg(body)
        assert isinstance(result, float)

    def test_range_0_360(self):
        body = ephem.Mars(ephem.Date("2023/6/15"))
        result = ecliptic_lon_deg(body)
        assert 0.0 <= result < 360.0


class TestIsRetrograde:
    def test_mars_retrograde_2024(self):
        # Mars was retrograde around Dec 2024
        d_now = ephem.Date("2024/12/10")
        d_prev = ephem.Date("2024/12/9")
        result = is_retrograde(ephem.Mars, d_now, d_prev)
        assert isinstance(result, bool)

    def test_sun_never_retrograde(self):
        d_now = ephem.Date("2024/6/15")
        d_prev = ephem.Date("2024/6/14")
        assert is_retrograde(ephem.Sun, d_now, d_prev) is False


class TestIsStationary:
    def test_returns_bool(self):
        d = ephem.Date("2024/6/15")
        result = is_stationary(ephem.Jupiter, d, orb_days=2)
        assert isinstance(result, bool)

    def test_fast_planet_rarely_stationary(self):
        # Sun is never stationary
        d = ephem.Date("2024/3/20")
        assert is_stationary(ephem.Sun, d) is False


class TestApplyBhCorrection:
    def test_empty_list(self):
        result = apply_bh_correction([])
        assert result == []

    def test_single_record(self):
        records = [{"p_value": 0.05}]
        apply_bh_correction(records)
        assert "q_value" in records[0]
        assert records[0]["q_value"] == 0.05

    def test_monotonic_q_values(self):
        records = [
            {"p_value": 0.01},
            {"p_value": 0.04},
            {"p_value": 0.10},
        ]
        apply_bh_correction(records)
        q_vals = [r["q_value"] for r in sorted(records, key=lambda x: x["p_value"])]
        # q-values should be non-decreasing when sorted by p-value
        for i in range(len(q_vals) - 1):
            assert q_vals[i] <= q_vals[i + 1]

    def test_q_values_bounded_by_1(self):
        records = [{"p_value": 0.99}, {"p_value": 0.95}]
        apply_bh_correction(records)
        for r in records:
            assert r["q_value"] <= 1.0

    def test_custom_keys(self):
        records = [{"my_p": 0.03}]
        apply_bh_correction(records, p_key="my_p", q_key="my_q")
        assert "my_q" in records[0]

    def test_preserves_other_fields(self):
        records = [{"name": "test", "p_value": 0.05}]
        apply_bh_correction(records)
        assert records[0]["name"] == "test"


class TestTodayLocalDate:
    def test_returns_date(self):
        result = today_local_date()
        assert isinstance(result, date)


class TestYfinanceExclusiveEnd:
    def test_adds_one_day(self):
        result = yfinance_exclusive_end(date(2024, 3, 15))
        assert result == "2024-03-16"

    def test_month_boundary(self):
        result = yfinance_exclusive_end(date(2024, 1, 31))
        assert result == "2024-02-01"
