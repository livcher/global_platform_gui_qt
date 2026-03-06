"""
ToolVersionService - Manages custom GP and FDSM tool versions.

Handles fetching available versions from GitHub releases, downloading JARs,
and resolving paths to the active tool version.
"""

import json
import os
import re
import subprocess
import sys
import urllib.request
import urllib.error
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

from secure_storage import get_app_data_dir
from src.views.dialogs.plugin_designer.utils import GitHubError


TOOLS_DIR = get_app_data_dir() / "tools"

# GitHub repo coordinates
GP_OWNER = "martinpaljak"
GP_REPO = "GlobalPlatformPro"
GP_JAR_NAME = "gp.jar"

FDSM_OWNER = "fidesmo"
FDSM_REPO = "fdsm"
FDSM_JAR_NAME = "fdsm.jar"


@dataclass
class ReleaseInfo:
    """Information about a GitHub release."""
    tag: str
    name: str
    jar_download_url: str


class ToolVersionService:
    """Service for managing GP and FDSM tool versions."""

    @staticmethod
    def fetch_releases(
        owner: str, repo: str, jar_name: str, max_pages: int = 3
    ) -> List[ReleaseInfo]:
        """
        Fetch releases that contain the specified JAR asset.

        Uses GitHub REST API with pagination. Returns releases sorted
        newest-first (GitHub's default order).

        Args:
            owner: Repository owner
            repo: Repository name
            jar_name: JAR filename to look for in release assets
            max_pages: Maximum number of pages to fetch (30 releases per page)

        Returns: List of ReleaseInfo for releases containing the JAR

        Raises: GitHubError on failure
        """
        releases = []
        page = 1

        while page <= max_pages:
            api_url = (
                f"https://api.github.com/repos/{owner}/{repo}/releases"
                f"?per_page=30&page={page}"
            )

            try:
                req = urllib.request.Request(api_url)
                req.add_header("Accept", "application/vnd.github.v3+json")
                req.add_header("User-Agent", "GlobalPlatformGUI")

                with urllib.request.urlopen(req, timeout=15) as response:
                    data = json.loads(response.read().decode())

                if not data:
                    break

                for release in data:
                    if release.get("draft"):
                        continue
                    tag = release.get("tag_name", "")
                    name = release.get("name", "") or tag
                    for asset in release.get("assets", []):
                        if asset.get("name") == jar_name:
                            releases.append(
                                ReleaseInfo(
                                    tag=tag,
                                    name=name,
                                    jar_download_url=asset.get(
                                        "browser_download_url", ""
                                    ),
                                )
                            )
                            break

                if len(data) < 30:
                    break
                page += 1

            except urllib.error.HTTPError as e:
                if e.code == 404:
                    raise GitHubError(
                        f"Repository '{owner}/{repo}' not found", 404
                    )
                elif e.code == 403:
                    raise GitHubError(
                        "GitHub API rate limit exceeded. Try again later.", 403
                    )
                else:
                    raise GitHubError(
                        f"GitHub API error: {e.code} {e.reason}", e.code
                    )
            except urllib.error.URLError as e:
                raise GitHubError(f"Network error: {e.reason}")
            except GitHubError:
                raise
            except Exception as e:
                raise GitHubError(f"Error fetching releases: {e}")

        return releases

    @staticmethod
    def get_tool_path(tool_name: str, tag: str) -> Path:
        """Get the expected local path for a downloaded tool version."""
        return TOOLS_DIR / tool_name / tag / f"{tool_name}.jar"

    @staticmethod
    def is_version_downloaded(tool_name: str, tag: str) -> bool:
        """Check if a specific version is already downloaded."""
        return ToolVersionService.get_tool_path(tool_name, tag).exists()

    @staticmethod
    def download_tool(
        tool_name: str,
        tag: str,
        download_url: str,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> Path:
        """
        Download a tool JAR to the local tools directory.

        Args:
            tool_name: Tool identifier ("gp" or "fdsm")
            tag: Release tag (used as subdirectory name)
            download_url: URL to download the JAR from
            progress_callback: Optional callback(bytes_read, total_bytes)

        Returns: Path to the downloaded file

        Raises: Exception on download failure
        """
        dest_path = ToolVersionService.get_tool_path(tool_name, tag)
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        req = urllib.request.Request(download_url)
        req.add_header("User-Agent", "GlobalPlatformGUI")

        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                total = int(response.headers.get("Content-Length", 0))
                bytes_read = 0
                chunk_size = 65536

                with open(dest_path, "wb") as f:
                    while True:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        bytes_read += len(chunk)
                        if progress_callback:
                            progress_callback(bytes_read, total)

        except Exception:
            # Clean up partial download
            if dest_path.exists():
                dest_path.unlink()
            raise

        return dest_path

    @staticmethod
    def resolve_gp_path(custom_version: Optional[str]) -> Optional[str]:
        """
        Resolve the GP JAR path for the given version selection.

        Returns None if built-in should be used (no custom version selected
        or custom JAR is missing from disk).
        Returns path string if custom version exists on disk.
        """
        if not custom_version:
            return None
        path = ToolVersionService.get_tool_path("gp", custom_version)
        return str(path) if path.exists() else None

    @staticmethod
    def resolve_fdsm_path(custom_version: Optional[str]) -> Optional[str]:
        """
        Resolve the FDSM JAR path for the given version selection.

        Returns None if built-in should be used (no custom version selected
        or custom JAR is missing from disk).
        Returns path string if custom version exists on disk.
        """
        if not custom_version:
            return None
        path = ToolVersionService.get_tool_path("fdsm", custom_version)
        return str(path) if path.exists() else None

    @staticmethod
    def detect_bundled_gp_version() -> Optional[str]:
        """
        Detect the version of the bundled gp.jar by reading its manifest.

        Returns a short commit hash (e.g. "f2af9ef") or None if detection fails.
        This is instant since it reads the JAR directly without running Java.
        """
        from .gp_service import resource_path

        try:
            jar_path = resource_path("gp.jar")
            if not os.path.exists(jar_path):
                return None
            with zipfile.ZipFile(jar_path) as z:
                manifest = z.read("META-INF/MANIFEST.MF").decode()
            match = re.search(r"Last-Commit-Id:\s*([0-9a-fA-F]+)", manifest)
            if match:
                return match.group(1)[:7]
        except Exception:
            pass
        return None

    @staticmethod
    def detect_bundled_fdsm_version() -> Optional[str]:
        """
        Detect the version of the bundled fdsm.jar by running --version.

        Returns a version tag (e.g. "v26.01.02") or None if detection fails.
        """
        from .gp_service import resource_path

        try:
            jar_path = resource_path("fdsm.jar")
            if not os.path.exists(jar_path):
                return None
            flags = {}
            if sys.platform == "win32":
                flags["creationflags"] = subprocess.CREATE_NO_WINDOW
            result = subprocess.run(
                ["java", "-jar", jar_path, "--version"],
                capture_output=True, text=True, timeout=10, **flags,
            )
            output = result.stdout or result.stderr or ""
            # Parse "# fdsm v26.01.02-0-ge17021f" → "v26.01.02"
            match = re.search(r"fdsm\s+(v[\d.]+)", output)
            if match:
                return match.group(1)
        except Exception:
            pass
        return None
