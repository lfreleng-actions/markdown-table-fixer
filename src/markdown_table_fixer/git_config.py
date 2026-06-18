# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025 The Linux Foundation

"""Git configuration management for commit signing and user identity."""

from __future__ import annotations

from enum import Enum
import logging
from pathlib import Path  # noqa: TC003
import subprocess

logger = logging.getLogger(__name__)


# Inherit from (str, Enum) rather than enum.StrEnum to preserve Python
# 3.10 support (StrEnum was only added in 3.11; see requires-python).
class GitConfigMode(str, Enum):  # noqa: UP042
    """Git configuration modes."""

    USER_INHERIT = (
        "user_inherit"  # Inherit user's full config including signing
    )
    USER_NO_SIGN = "user_no_sign"  # Use user identity but disable signing
    BOT_IDENTITY = "bot_identity"  # Use bot identity without signing


def _get_global_git_config(key: str) -> str | None:
    """Get a value from global git config.

    Args:
        key: Git config key (e.g., "user.name")

    Returns:
        Config value or None if not set
    """
    try:
        result = subprocess.run(
            ["git", "config", "--global", key],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            value = result.stdout.strip()
            return value if value else None
        return None
    except Exception as e:
        logger.debug(f"Could not get git config {key}: {e}")
        return None


def _set_repo_git_config(repo_dir: Path, key: str, value: str) -> bool:
    """Set a git config value in the repository.

    Args:
        repo_dir: Repository directory path
        key: Git config key
        value: Value to set

    Returns:
        True if successful, False otherwise
    """
    try:
        subprocess.run(
            ["git", "config", key, value],
            cwd=repo_dir,
            check=True,
            capture_output=True,
        )
        return True
    except Exception as e:
        logger.debug(f"Could not set git config {key}={value}: {e}")
        return False


def configure_git_identity(
    repo_dir: Path,
    mode: str = GitConfigMode.USER_INHERIT,
    *,
    bot_name: str = "markdown-table-fixer",
    bot_email: str = "noreply@linuxfoundation.org",
) -> dict[str, str]:
    """Configure git identity and signing settings in a repository.

    Args:
        repo_dir: Repository directory path
        mode: Configuration mode (USER_INHERIT, USER_NO_SIGN, or BOT_IDENTITY)
        bot_name: Bot name for BOT_IDENTITY mode
        bot_email: Bot email for BOT_IDENTITY mode

    Returns:
        Dict with applied configuration details

    Raises:
        ValueError: If mode is invalid
    """
    valid_modes = [m.value for m in GitConfigMode]
    if mode not in valid_modes:
        msg = f"Invalid mode: {mode}. Must be one of {valid_modes}"
        raise ValueError(msg)

    applied_config: dict[str, str] = {}

    if mode == GitConfigMode.BOT_IDENTITY:
        # Use bot identity without signing
        logger.debug("Configuring git with bot identity (no signing)")
        if _set_repo_git_config(repo_dir, "user.name", bot_name):
            applied_config["user.name"] = bot_name
        else:
            logger.warning(f"Failed to set user.name to {bot_name}")

        if _set_repo_git_config(repo_dir, "user.email", bot_email):
            applied_config["user.email"] = bot_email
        else:
            logger.warning(f"Failed to set user.email to {bot_email}")

        applied_config["mode"] = "bot_identity"
        return applied_config

    # For USER_INHERIT and USER_NO_SIGN modes, try to get user's config
    user_name = _get_global_git_config("user.name")
    user_email = _get_global_git_config("user.email")

    if not user_name or not user_email:
        logger.warning(
            "User git config not found, falling back to bot identity"
        )
        if _set_repo_git_config(repo_dir, "user.name", bot_name):
            applied_config["user.name"] = bot_name
        else:
            logger.warning(f"Failed to set user.name to {bot_name}")

        if _set_repo_git_config(repo_dir, "user.email", bot_email):
            applied_config["user.email"] = bot_email
        else:
            logger.warning(f"Failed to set user.email to {bot_email}")

        applied_config["mode"] = "bot_identity_fallback"
        return applied_config

    # Set user identity
    if _set_repo_git_config(repo_dir, "user.name", user_name):
        applied_config["user.name"] = user_name
    else:
        logger.warning(f"Failed to set user.name to {user_name}")

    if _set_repo_git_config(repo_dir, "user.email", user_email):
        applied_config["user.email"] = user_email
    else:
        logger.warning(f"Failed to set user.email to {user_email}")

    if mode == GitConfigMode.USER_NO_SIGN:
        # Explicitly disable signing
        logger.debug("Configuring git with user identity (signing disabled)")
        if _set_repo_git_config(repo_dir, "commit.gpgsign", "false"):
            applied_config["commit.gpgsign"] = "false"
        else:
            logger.warning("Failed to set commit.gpgsign to false")

        applied_config["mode"] = "user_no_sign"
        return applied_config

    # USER_INHERIT mode: copy signing configuration
    logger.debug("Configuring git with user identity (inheriting signing)")

    # Check if user has signing enabled
    gpgsign = _get_global_git_config("commit.gpgsign")
    if gpgsign == "true":
        if _set_repo_git_config(repo_dir, "commit.gpgsign", "true"):
            applied_config["commit.gpgsign"] = "true"
        else:
            logger.warning("Failed to set commit.gpgsign to true")

        # Get GPG format (ssh, openpgp, x509) - default to openpgp if not set
        gpg_format = _get_global_git_config("gpg.format") or "openpgp"
        if _set_repo_git_config(repo_dir, "gpg.format", gpg_format):
            applied_config["gpg.format"] = gpg_format
        else:
            logger.warning(f"Failed to set gpg.format to {gpg_format}")

        # Handle SSH-specific configuration
        if gpg_format == "ssh":
            # Copy SSH signing key
            ssh_key = _get_global_git_config("user.signingkey")
            if ssh_key:
                if _set_repo_git_config(repo_dir, "user.signingkey", ssh_key):
                    applied_config["user.signingkey"] = ssh_key
                else:
                    logger.warning(
                        f"Failed to set user.signingkey to {ssh_key}"
                    )

            # Copy allowed signers file
            allowed_signers = _get_global_git_config(
                "gpg.ssh.allowedSignersFile"
            )
            if allowed_signers:
                if _set_repo_git_config(
                    repo_dir, "gpg.ssh.allowedSignersFile", allowed_signers
                ):
                    applied_config["gpg.ssh.allowedSignersFile"] = (
                        allowed_signers
                    )
                else:
                    logger.warning(
                        f"Failed to set gpg.ssh.allowedSignersFile to {allowed_signers}"
                    )

            # Copy default key ID if set
            default_key = _get_global_git_config("gpg.ssh.defaultKeyCommand")
            if default_key:
                if _set_repo_git_config(
                    repo_dir, "gpg.ssh.defaultKeyCommand", default_key
                ):
                    applied_config["gpg.ssh.defaultKeyCommand"] = default_key
                else:
                    logger.warning(
                        f"Failed to set gpg.ssh.defaultKeyCommand to {default_key}"
                    )

        # Handle GPG-specific configuration (openpgp, x509)
        elif gpg_format in ["openpgp", "x509"]:
            # Copy GPG signing key
            signing_key = _get_global_git_config("user.signingkey")
            if signing_key:
                if _set_repo_git_config(
                    repo_dir, "user.signingkey", signing_key
                ):
                    applied_config["user.signingkey"] = signing_key
                else:
                    logger.warning(
                        f"Failed to set user.signingkey to {signing_key}"
                    )

            # Copy GPG program if specified
            gpg_program = _get_global_git_config("gpg.program")
            if gpg_program:
                if _set_repo_git_config(repo_dir, "gpg.program", gpg_program):
                    applied_config["gpg.program"] = gpg_program
                else:
                    logger.warning(
                        f"Failed to set gpg.program to {gpg_program}"
                    )

        logger.debug(
            f"Git signing enabled: format={gpg_format}, "
            f"key={'configured' if applied_config.get('user.signingkey') else 'default'}"
        )
    else:
        logger.debug("User does not have commit signing enabled")

    applied_config["mode"] = "user_inherit"
    return applied_config


def get_signing_info(repo_dir: Path) -> dict[str, str | bool]:
    """Get current signing configuration from a repository.

    Args:
        repo_dir: Repository directory path

    Returns:
        Dict with signing configuration details
    """
    info: dict[str, str | bool] = {}

    try:
        result = subprocess.run(
            ["git", "config", "commit.gpgsign"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            check=False,
        )
        info["signing_enabled"] = result.stdout.strip() == "true"

        if info["signing_enabled"]:
            # Get format
            result = subprocess.run(
                ["git", "config", "gpg.format"],
                cwd=repo_dir,
                capture_output=True,
                text=True,
                check=False,
            )
            gpg_format = result.stdout.strip()
            info["format"] = gpg_format if gpg_format else "openpgp"

            # Get signing key
            result = subprocess.run(
                ["git", "config", "user.signingkey"],
                cwd=repo_dir,
                capture_output=True,
                text=True,
                check=False,
            )
            signing_key = result.stdout.strip()
            if signing_key:
                info["signing_key"] = signing_key

    except Exception as e:
        logger.debug(f"Could not get signing info: {e}")

    return info
