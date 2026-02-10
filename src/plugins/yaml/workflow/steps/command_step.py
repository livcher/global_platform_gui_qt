"""
Command Step

Executes shell commands as part of plugin workflows.
External commands require first-run user consent per plugin.
"""

import subprocess
import shlex
import sys
from typing import Any, Optional

from ..context import WorkflowContext
from .base import BaseStep, StepResult, StepError
from ...encoding.encoder import TemplateProcessor

# Windows-specific: hide console window when running subprocesses
_SUBPROCESS_FLAGS = {}
if sys.platform == "win32":
    _SUBPROCESS_FLAGS["creationflags"] = subprocess.CREATE_NO_WINDOW


# Commands that are never allowed regardless of consent.
# These have no legitimate use in smartcard plugin workflows.
BLOCKED_COMMANDS = frozenset({
    "rm", "rmdir", "del",           # Deletion
    "dd", "shred",                   # Raw disk / destructive write
    "mkfs", "fdisk", "parted",       # Filesystem / partition
    "shutdown", "reboot", "halt",    # System power
    "kill", "killall", "pkill",      # Process killing
    "chmod", "chown", "chgrp",       # Permission changes
    "sudo", "su", "doas",           # Privilege escalation
    "curl", "wget",                  # Network downloads (use source.type instead)
    "nc", "ncat", "netcat", "socat", # Network tools
    "python", "python3", "perl",     # Script interpreters (use script steps instead)
    "bash", "sh", "zsh", "cmd",      # Shell interpreters
    "powershell", "pwsh",            # PowerShell
})


class CommandStep(BaseStep):
    """
    Executes a shell command.

    Commands can use template variables from the context.
    Stdout/stderr are captured and stored in the workflow context.

    Security:
    - Blocked commands are always rejected (BLOCKED_COMMANDS).
    - A consent_service must be registered on the context for
      commands to run. Without it, execution is denied (default-deny).
    - On first execution per plugin, user consent is requested
      via the consent_service.
    """

    def __init__(
        self,
        step_id: str,
        command: list[str],
        name: Optional[str] = None,
        description: Optional[str] = None,
        depends_on: Optional[list[str]] = None,
        timeout: int = 60,
        capture_output: bool = True,
        plugin_name: Optional[str] = None,
    ):
        """
        Initialize the command step.

        Args:
            step_id: Step identifier
            command: Command and arguments as list
            name: Human-readable name
            description: Description shown during execution
            depends_on: Step dependencies
            timeout: Command timeout in seconds
            capture_output: Whether to capture stdout/stderr
            plugin_name: Plugin name for consent tracking
        """
        super().__init__(step_id, name, description, depends_on)
        self.command = command
        self.timeout = timeout
        self.capture_output = capture_output
        self.plugin_name = plugin_name

    def execute(self, context: WorkflowContext) -> StepResult:
        """Execute the shell command."""
        context.report_progress(
            self.description or f"Running {self.name}..."
        )

        # Validate command
        if not self.command:
            return StepResult.fail("No command specified")

        # Check blocklist before any processing
        base_cmd = self.command[0].split("/")[-1].split("\\")[-1].lower()
        if base_cmd in BLOCKED_COMMANDS:
            return StepResult.fail(
                f"Command '{base_cmd}' is blocked for security reasons"
            )

        # Process template variables in command
        variables = context.get_all_variables()
        processed_cmd = []
        for arg in self.command:
            processed = TemplateProcessor.process(arg, variables)
            processed_cmd.append(processed)

        # Default-deny: require consent service for command execution
        consent_service = context.get_service("consent_service")
        if not consent_service:
            return StepResult.fail(
                "Command execution requires a consent service. "
                "Commands can only run from the management panel."
            )

        if self.plugin_name:
            if not consent_service.check_or_request(
                self.plugin_name, " ".join(processed_cmd)
            ):
                return StepResult.fail(
                    "User declined external command execution"
                )

        try:
            result = subprocess.run(
                processed_cmd,
                capture_output=self.capture_output,
                text=True,
                timeout=self.timeout,
                cwd=str(context.temp_dir),
                **_SUBPROCESS_FLAGS,
            )

            if result.returncode != 0:
                error_msg = result.stderr or f"Command exited with code {result.returncode}"
                return StepResult.fail(error_msg)

            return StepResult.ok({
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            })

        except subprocess.TimeoutExpired:
            return StepResult.fail(f"Command timed out after {self.timeout} seconds")
        except FileNotFoundError:
            return StepResult.fail(
                f"Command not found: {processed_cmd[0]}. "
                f"Please ensure the tool is installed and in your PATH."
            )
        except Exception as e:
            return StepResult.fail(f"Command execution failed: {e}")

    def validate(self, context: WorkflowContext) -> Optional[str]:
        """Validate the command."""
        if not self.command:
            return "No command specified"

        base_cmd = self.command[0].split("/")[-1].split("\\")[-1].lower()
        if base_cmd in BLOCKED_COMMANDS:
            return f"Command '{base_cmd}' is blocked for security reasons"

        return None
