import re

from app.config import get_settings

_settings = get_settings()
MAX_CODE_SIZE = _settings.MAX_CODE_SIZE
MAX_REQUIREMENTS_SIZE = _settings.MAX_REQUIREMENTS_SIZE
MAX_FILE_SIZE_BYTES = _settings.MAX_FILE_SIZE_BYTES


def get_max_file_size() -> int:
    """Return the current runtime limit for a single file in bytes."""
    return get_settings().MAX_FILE_SIZE_BYTES


def get_max_requirements_size() -> int:
    """Return the current runtime limit for ``requirements.txt`` in bytes."""
    return get_settings().MAX_REQUIREMENTS_SIZE


def validate_byte_length(value: str, max_bytes: int, field_name: str) -> str:
    if len(value.encode("utf-8")) > max_bytes:
        raise ValueError(f"{field_name} exceeds {max_bytes} bytes")
    return value


ALLOWED_FILE_EXTENSIONS = {
    ".py",
    ".txt",
    ".md",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".env",
    ".csv",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".webp",
    ".ico",
    ".pdf",
    ".mp3",
    ".mp4",
    ".webm",
    ".ogg",
    ".wav",
    ".ttf",
    ".woff",
    ".woff2",
}

MAX_LOGIN_LEN = 40

_SEGMENT_RE = re.compile(
    r"^[a-z0-9](?:[a-z0-9-]{0," + str(MAX_LOGIN_LEN - 2) + r"}[a-z0-9])?$"
)
_FILE_SEGMENT_RE = re.compile(r"^[a-zA-Z0-9_.-]+$")
_CONTENT_TYPE_RE = re.compile(r"^[-\w.]+/[-\w.+]+$")


def validate_content_type(value: str) -> str:
    """Validate a MIME content type string.

    Parameters (e.g. ``; charset=utf-8``) are stripped and only the base
    media type is validated.

    Args:
        value: Raw content type string.

    Returns:
        The stripped base media type.

    Raises:
        ValueError: If the value is not a string or the base media type
            does not match the allowed MIME type pattern.
    """
    if not isinstance(value, str):
        raise ValueError("content_type must be a string")
    value = value.strip()
    base = value.split(";", 1)[0].strip()
    if not base or not _CONTENT_TYPE_RE.match(base):
        raise ValueError(f"Invalid content_type: {value!r}")
    return base


def validate_slug(value: str) -> str:
    """Normalize and validate a URL/path segment slug.

    Args:
        value: Raw slug string.

    Returns:
        Normalized slug: leading/trailing whitespace removed, any sequence of
        characters other than ASCII letters, digits, or hyphens replaced with a
        single hyphen, and lowercased.

    Raises:
        ValueError: If the normalized slug is empty, longer than 40 characters,
            starts or ends with a hyphen, or contains characters other than
            lowercase alphanumeric and (internal) hyphens.
    """
    value = re.sub(r"[^a-zA-Z0-9-]+", "-", value.strip()).lower()
    if not value or len(value) > 40 or not _SEGMENT_RE.match(value):
        raise ValueError(f"Invalid slug: {value!r}")
    return value


def validate_login(value: str) -> str:
    """Normalize and validate a user login identifier.

    Args:
        value: Raw login string.

    Returns:
        Normalized login: leading/trailing whitespace removed and lowercased.
        The returned value matches the allowed segment pattern.

    Raises:
        ValueError: If the normalized login is empty, longer than
            ``MAX_LOGIN_LEN`` characters, starts or ends with a hyphen, or
            contains characters other than lowercase alphanumeric and
            (internal) hyphens.
    """
    value = value.strip().lower()
    if not value or len(value) > MAX_LOGIN_LEN or not _SEGMENT_RE.match(value):
        raise ValueError(f"Invalid login: {value!r}")
    return value


def validate_file_path(value: str) -> str:
    """Validate a relative file path and its extension.

    Args:
        value: Raw relative file path string.

    Returns:
        The whitespace-stripped path. The extension check is case-insensitive,
        but the returned path preserves the input casing.

    Raises:
        ValueError: If the path is empty, longer than 255 characters, starts
            with a slash (absolute path), contains parent directory traversal
            (".."), contains double slashes ("//"), uses disallowed characters
            in any segment, or has a file extension that is not in
            ``ALLOWED_FILE_EXTENSIONS``.
    """
    value = value.strip()
    if not value:
        raise ValueError("Invalid file path: ''")
    if len(value) > 255:
        raise ValueError(f"File path too long: {len(value)} characters")
    if value.startswith("/"):
        raise ValueError(f"Invalid file path: absolute path: {value!r}")
    if "//" in value:
        raise ValueError(f"Invalid file path: contains double slash: {value!r}")

    segments = value.split("/")
    for segment in segments:
        if not segment:
            raise ValueError(f"Invalid file path: empty segment in {value!r}")
        if segment in (".", ".."):
            raise ValueError(f"Invalid file path: {segment!r}")
        if not _FILE_SEGMENT_RE.match(segment):
            raise ValueError(
                f"Invalid file path: invalid characters in segment: {segment!r}"
            )

    basename = segments[-1]
    if "." not in basename:
        raise ValueError(f"Invalid file path: no file extension: {basename!r}")
    ext = "." + basename.rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_FILE_EXTENSIONS:
        raise ValueError(f"File extension not allowed: {ext}")
    return value
