# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025 The Linux Foundation

"""Test organization-name normalization from CLI input.

These tests guard against incomplete URL substring sanitization: the
``github.com`` prefix must only be stripped when it is the actual host
of the supplied value, not when it merely appears somewhere in the
string.
"""

import pytest

from markdown_table_fixer.cli import _normalize_org_name


@pytest.mark.parametrize(
    ("supplied", "expected"),
    [
        # Bare organization names are returned unchanged.
        ("myorg", "myorg"),
        ("  myorg  ", "myorg"),
        # Genuine GitHub URLs/hosts have their prefix stripped.
        ("github.com/myorg", "myorg"),
        ("//github.com/myorg", "myorg"),
        ("https://github.com/myorg", "myorg"),
        ("http://github.com/myorg", "myorg"),
        ("https://www.github.com/myorg", "myorg"),
        ("https://github.com/myorg/", "myorg"),
        ("https://github.com/myorg/repo", "myorg"),
    ],
)
def test_normalize_org_name_valid(supplied: str, expected: str) -> None:
    """Legitimate org values resolve to the bare organization name."""
    assert _normalize_org_name(supplied) == expected


@pytest.mark.parametrize(
    "supplied",
    [
        # ``github.com`` appears in the value but is not the host; the
        # value must not be treated as a GitHub URL.
        "evil-github.com.example/payload",
        "notgithub.com/foo",
        "github.com.attacker.test/victim",
        # Surrounding whitespace is stripped before the host check.
        "  notgithub.com/foo  ",
    ],
)
def test_normalize_org_name_rejects_lookalike_hosts(supplied: str) -> None:
    """Look-alike hosts are not mistaken for github.com."""
    # No GitHub prefix stripping is applied: the value is returned with
    # only surrounding whitespace and leading/trailing slashes stripped
    # (whitespace is stripped first by the helper).
    assert _normalize_org_name(supplied) == supplied.strip().strip("/")


@pytest.mark.parametrize(
    "supplied",
    [
        "https://github.com",
        "https://github.com/",
        "github.com",
        "//www.github.com/",
    ],
)
def test_normalize_org_name_requires_org_segment(supplied: str) -> None:
    """A GitHub host without an org segment fails fast."""
    with pytest.raises(ValueError, match="No organization found"):
        _normalize_org_name(supplied)
