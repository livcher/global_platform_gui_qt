"""
Plugin Dependency Checker

Validates that required external commands are available on the system.
"""

import shutil
from dataclasses import dataclass
from typing import Optional

from .schema import CommandDependency, DependenciesDefinition


@dataclass
class DependencyCheckResult:
    """Result of checking a single command dependency."""
    dependency: CommandDependency
    available: bool
    path: Optional[str] = None

    @property
    def is_satisfied(self) -> bool:
        """A dependency is satisfied if available or optional."""
        return self.available or not self.dependency.required


class DependencyChecker:
    """Checks plugin dependencies against the system environment."""

    @staticmethod
    def check_command(name: str) -> tuple[bool, Optional[str]]:
        """Check if a command is available on the system."""
        path = shutil.which(name)
        return (path is not None, path)

    @classmethod
    def check_dependencies(
        cls, dependencies: Optional[DependenciesDefinition]
    ) -> list[DependencyCheckResult]:
        """Check all plugin dependencies. Returns empty list if none declared."""
        if not dependencies:
            return []

        results = []
        for cmd_dep in dependencies.commands:
            available, path = cls.check_command(cmd_dep.name)
            results.append(DependencyCheckResult(cmd_dep, available, path))

        return results

    @classmethod
    def get_missing_required(
        cls, results: list[DependencyCheckResult]
    ) -> list[DependencyCheckResult]:
        """Filter to only missing required dependencies."""
        return [r for r in results if not r.is_satisfied]
