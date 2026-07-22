# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025 The Linux Foundation

"""Module for tracking markdownlint disable/enable comments in markdown files."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path  # noqa: TC003
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import TableViolation


@dataclass
class DisabledRulesState:
    """Tracks which markdownlint rules are disabled at a given line in a file."""

    disabled_rules: set[str] = field(default_factory=set)
    """Set of currently disabled rule codes (e.g., {'MD013', 'MD060'})"""

    def is_rule_disabled(self, rule: str) -> bool:
        """Check if a specific rule is currently disabled.

        Args:
            rule: Rule code to check (e.g., 'MD013')

        Returns:
            True if the rule is disabled
        """
        return rule in self.disabled_rules

    def disable_rules(self, rules: set[str]) -> None:
        """Disable one or more rules.

        Args:
            rules: Set of rule codes to disable
        """
        self.disabled_rules.update(rules)

    def enable_rules(self, rules: set[str]) -> None:
        """Enable one or more rules (remove from disabled set).

        Args:
            rules: Set of rule codes to enable
        """
        self.disabled_rules -= rules

    def copy(self) -> DisabledRulesState:
        """Create a copy of this state.

        Returns:
            New DisabledRulesState with same disabled rules
        """
        return DisabledRulesState(disabled_rules=self.disabled_rules.copy())


class RuleDisabler:
    """Tracks markdownlint disable/enable comments throughout a file."""

    def __init__(self, file_path: Path):
        """Initialize rule disabler.

        Args:
            file_path: Path to the markdown file
        """
        self.file_path = file_path
        self._line_states: dict[int, DisabledRulesState] = {}
        self._parsed = False

    def parse_file(self) -> None:
        """Parse the file and build a map of disabled rules per line."""
        if self._parsed:
            return

        try:
            with open(self.file_path, encoding="utf-8") as f:
                lines = f.readlines()
        except OSError:
            # If file can't be read, assume no rules are disabled
            self._parsed = True
            return

        # Track current state as we go through the file
        current_state = DisabledRulesState()

        for line_num, line in enumerate(lines, start=1):
            disabled_rules = self._parse_markdownlint_comment(line, "disable")
            if disabled_rules:
                current_state.disable_rules(disabled_rules)

            enabled_rules = self._parse_markdownlint_comment(line, "enable")
            if enabled_rules:
                current_state.enable_rules(enabled_rules)

            # Store a copy of the state for this line
            self._line_states[line_num] = current_state.copy()

        self._parsed = True

    def is_rule_disabled_at_line(self, line_number: int, rule: str) -> bool:
        """Check if a specific rule is disabled at a given line.

        Args:
            line_number: Line number (1-indexed)
            rule: Rule code to check (e.g., 'MD013')

        Returns:
            True if the rule is disabled at that line
        """
        if not self._parsed:
            self.parse_file()

        state = self._line_states.get(line_number)
        if state is None:
            return False

        return state.is_rule_disabled(rule)

    def get_disabled_rules_at_line(self, line_number: int) -> set[str]:
        """Get all disabled rules at a given line.

        Args:
            line_number: Line number (1-indexed)

        Returns:
            Set of disabled rule codes
        """
        if not self._parsed:
            self.parse_file()

        state = self._line_states.get(line_number)
        if state is None:
            return set()

        return state.disabled_rules.copy()

    def _parse_markdownlint_comment(
        self, line: str, comment_type: str
    ) -> set[str]:
        """Parse a markdownlint disable/enable comment.

        Args:
            line: The line to parse
            comment_type: Either "disable" or "enable"

        Returns:
            Set of rule names found in the comment (e.g., {"MD013", "MD060"})
        """
        # Match markdownlint comments with word boundaries for rule names
        # Examples:
        #   <!-- markdownlint-disable MD013 MD060 -->
        #   <!-- markdownlint-enable MD013 -->
        pattern = rf"<!--\s*markdownlint-{comment_type}\s+(.*?)\s*-->"
        match = re.search(pattern, line)
        if not match:
            return set()

        rules_text = match.group(1)
        # Match MD followed by digits, using word boundaries to avoid false matches
        rule_pattern = r"\bMD\d+\b"
        rules = re.findall(rule_pattern, rules_text)
        return set(rules)


def filter_violations_by_disabled_rules(
    violations: list[TableViolation],
    file_path: Path,
) -> list[TableViolation]:
    """Filter out violations that are in sections with disabled rules.

    Args:
        violations: List of TableViolation objects
        file_path: Path to the file being checked

    Returns:
        Filtered list of violations with disabled rules removed
    """
    if not violations:
        return violations

    disabler = RuleDisabler(file_path)
    disabler.parse_file()

    # Filter violations
    filtered = []
    for violation in violations:
        # Check if this violation's rule is disabled at its line
        if not disabler.is_rule_disabled_at_line(
            violation.line_number, violation.md_rule
        ):
            filtered.append(violation)

    return filtered
