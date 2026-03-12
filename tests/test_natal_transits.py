"""Unit tests for research/astro_natal_transits_test.py — natal transit calculations."""

import math
from datetime import datetime

import ephem
import pytest

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "research"))

from astro_natal_transits_test import (
    angular_distance_deg,
    build_natal_positions,
    is_retrograde,
    longitude_deg,
    parse_birth_specs,
    ASPECTS,
    ASPECT_ORB_RATIOS,
)


class TestAngularDistanceDeg:
    def test_same_point(self):
        assert angular_distance_deg(100.0, 100.0) == 0.0

    def test_opposite(self):
        assert angular_distance_deg(0.0, 180.0) == 180.0

    def test_wrapping(self):
        assert angular_distance_deg(10.0, 350.0) == 20.0

    def test_symmetry(self):
        d1 = angular_distance_deg(30.0, 270.0)
        d2 = angular_distance_deg(270.0, 30.0)
        assert d1 == d2

    @pytest.mark.parametrize("a,b,expected", [
        (0, 90, 90),
        (0, 270, 90),
        (45, 315, 90),
        (180, 180, 0),
    ])
    def test_known_distances(self, a, b, expected):
        assert angular_distance_deg(float(a), float(b)) == expected

    def test_always_lte_180(self):
        for a in range(0, 360, 15):
            for b in range(0, 360, 15):
                assert angular_distance_deg(float(a), float(b)) <= 180.0


class TestLongitudeDeg:
    def test_returns_float(self):
        result = longitude_deg(ephem.Sun, datetime(2024, 6, 21))
        assert isinstance(result, float)

    def test_range(self):
        result = longitude_deg(ephem.Mars, datetime(2024, 1, 15))
        assert 0.0 <= result < 360.0


class TestIsRetrograde:
    def test_returns_bool(self):
        result = is_retrograde(ephem.Jupiter, datetime(2024, 6, 15))
        assert isinstance(result, bool)


class TestParseBirthSpecs:
    def test_named_spec(self):
        specs = ["genesis=2009-01-03T18:15:05"]
        result = parse_birth_specs(specs)
        assert len(result) == 1
        assert result[0][0] == "genesis"
        assert result[0][1] == datetime(2009, 1, 3, 18, 15, 5)

    def test_unnamed_spec(self):
        specs = ["2020-01-01T00:00:00"]
        result = parse_birth_specs(specs)
        assert result[0][0] == "custom"

    def test_multiple(self):
        specs = ["a=2020-01-01T00:00:00", "b=2021-06-15T12:00:00"]
        result = parse_birth_specs(specs)
        assert len(result) == 2


class TestBuildNatalPositions:
    def test_returns_all_bodies(self):
        positions = build_natal_positions(datetime(2009, 1, 3, 18, 15, 5))
        expected_bodies = {"Солнце", "Луна", "Меркурий", "Венера", "Марс", "Юпитер", "Сатурн"}
        assert set(positions.keys()) == expected_bodies

    def test_all_values_in_range(self):
        positions = build_natal_positions(datetime(2009, 1, 3, 18, 15, 5))
        for name, lon in positions.items():
            assert 0.0 <= lon < 360.0, f"{name} = {lon} out of range"


class TestAspectConfig:
    def test_all_aspects_have_orb_ratios(self):
        for aspect_name in ASPECTS:
            assert aspect_name in ASPECT_ORB_RATIOS, f"Missing orb ratio for {aspect_name}"

    def test_orb_ratios_positive(self):
        for name, ratio in ASPECT_ORB_RATIOS.items():
            assert ratio > 0, f"Orb ratio for {name} should be positive"
