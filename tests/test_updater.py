import sys

import pytest

from scripts.updater import _asset_name, _is_newer, _parse_version, is_frozen


@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        ("v1.2.3", (1, 2, 3)),
        ("1.2.3", (1, 2, 3)),
        ("v1.2", (1, 2, 0)),
        ("v2", (2, 0, 0)),
        ("v1.2.3-rc1", (1, 2, 3)),
        ("garbage", (0, 0, 0)),
        ("", (0, 0, 0)),
    ],
)
def test_parse_version(tag, expected):
    assert _parse_version(tag) == expected


@pytest.mark.parametrize(
    ("latest", "current", "expected"),
    [
        ("v0.2.0", "0.1.0", True),
        ("v0.1.0", "0.1.0", False),
        ("v0.0.9", "0.1.0", False),
        ("v1.0.0", "0.1.0", True),
    ],
)
def test_is_newer(latest, current, expected):
    assert _is_newer(latest, current) is expected


def test_asset_name_matches_current_release_convention():
    assert _asset_name("Linux", "x86_64") == "texflow-linux-x86_64"


def test_asset_name_is_platform_forward_compatible():
    assert _asset_name("Darwin", "arm64") == "texflow-darwin-arm64"


def test_is_frozen_true(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert is_frozen() is True


def test_is_frozen_false(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert is_frozen() is False
