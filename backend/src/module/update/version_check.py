import logging

import semver

from module.conf import VERSION, VERSION_PATH

logger = logging.getLogger(__name__)


def _is_semver(version: str) -> bool:
    try:
        semver.VersionInfo.parse(version)
        return True
    except ValueError:
        return False


def version_check() -> tuple[bool, int | None]:
    """Check if version has changed.

    Returns:
        A tuple of (is_same_version, last_minor_version).
        last_minor_version is None if no upgrade is needed.
    """
    if VERSION == "DEV_VERSION":
        return True, None
    if VERSION == "local":
        return True, None
    # CI 构建生成的分支版本号（如 lightmerge-fixes-2026-04-04-abc1234）不是合法 SemVer
    if not _is_semver(VERSION):
        logger.info("Non-SemVer version %r, skip version check", VERSION)
        return True, None
    if not VERSION_PATH.exists():
        with open(VERSION_PATH, "w") as f:
            f.write(VERSION + "\n")
        return False, None
    else:
        with open(VERSION_PATH, "r+") as f:
            # Read last version
            versions = f.readlines()
            last_version = versions[-1].strip()
            last_ver = semver.VersionInfo.parse(last_version)
            now_ver = semver.VersionInfo.parse(VERSION)
            if now_ver.minor == last_ver.minor:
                return True, None
            else:
                if now_ver.minor > last_ver.minor:
                    f.write(VERSION + "\n")
                    return False, last_ver.minor
                else:
                    return True, None
