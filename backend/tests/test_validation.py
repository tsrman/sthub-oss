import pytest
from app.core.validation import (
    validate_content_type,
    validate_file_path,
    validate_login,
    validate_slug,
)


def test_validate_slug_ok():
    assert validate_slug("my-app") == "my-app"
    assert validate_slug("My App") == "my-app"
    assert validate_slug("my_app") == "my-app"


def test_validate_slug_boundary_ok():
    assert validate_slug("a" * 40) == "a" * 40


def test_validate_slug_errors():
    with pytest.raises(ValueError):
        validate_slug("")
    with pytest.raises(ValueError):
        validate_slug("-app")
    with pytest.raises(ValueError):
        validate_slug("app-")
    with pytest.raises(ValueError):
        validate_slug("a" * 41)
    with pytest.raises(ValueError):
        validate_slug("  !  ")


def test_validate_slug_normalization_produces_invalid_slug():
    # "!" normalizes to "-", which is an invalid slug (leading/trailing hyphen).
    with pytest.raises(ValueError):
        validate_slug("!")


def test_validate_login_ok():
    # login must match [a-z0-9-]. A dotted Keycloak username such as "a.example"
    # is normalized to "a-example" when the user is auto-provisioned.
    assert validate_login("a-example") == "a-example"


def test_validate_login_boundary_ok():
    assert validate_login("a" + "b" * 38 + "c") == "a" + "b" * 38 + "c"


def test_validate_login_boundary_too_long():
    with pytest.raises(ValueError):
        validate_login("a" * 41)


def test_validate_login_leading_hyphen_rejected():
    with pytest.raises(ValueError):
        validate_login("-user")


def test_validate_login_trailing_hyphen_rejected():
    with pytest.raises(ValueError):
        validate_login("user-")


def test_validate_login_uppercase_normalized():
    assert validate_login("UserOne") == "userone"


def test_validate_file_path_ok():
    assert validate_file_path("app.py") == "app.py"
    assert validate_file_path("pages/dashboard.py") == "pages/dashboard.py"
    assert validate_file_path("assets/logo.png") == "assets/logo.png"
    assert validate_file_path(".env") == ".env"


def test_validate_file_path_dots_and_hidden_ok():
    # Dots are allowed inside directory/file names; hidden files are allowed.
    assert validate_file_path(".streamlit/config.toml") == ".streamlit/config.toml"
    assert validate_file_path(".hidden.py") == ".hidden.py"
    assert validate_file_path(".env") == ".env"


def test_validate_file_path_dot_py_basename_ok():
    # A hidden file whose entire basename is just the extension is still valid.
    assert validate_file_path(".py") == ".py"


def test_validate_file_path_uppercase_extension_normalized():
    # Extension check is case-insensitive; original casing is preserved.
    assert validate_file_path("image.PNG") == "image.PNG"


def test_validate_file_path_errors():
    with pytest.raises(ValueError):
        validate_file_path("")
    with pytest.raises(ValueError):
        validate_file_path("../etc/passwd")
    with pytest.raises(ValueError):
        validate_file_path("./file.py")
    with pytest.raises(ValueError):
        validate_file_path("app.exe")
    with pytest.raises(ValueError):
        validate_file_path("/absolute/path.py")
    with pytest.raises(ValueError):
        validate_file_path("archive.tar.gz")
    with pytest.raises(ValueError):
        validate_file_path("styles.css.map")


def test_validate_file_path_parent_traversal_in_middle_rejected():
    with pytest.raises(ValueError):
        validate_file_path("dir/../file.py")


def test_validate_file_path_double_slash_rejected():
    with pytest.raises(ValueError):
        validate_file_path("dir//file.py")


@pytest.mark.parametrize(
    "path",
    [
        "app\x00.py",
        "dir/\x00file.py",
        "dir/file.py/",
        "dir/ /file.py",
        "dir/file name.py",
        "dir\\file.py",
        "café.py",
        "/app.py",
        "  ",
    ],
)
def test_validate_file_path_edge_cases_rejected(path: str) -> None:
    with pytest.raises(ValueError):
        validate_file_path(path)


def test_validate_file_path_too_long_rejected():
    path = "a" * 252 + ".py"
    assert len(path) == 255
    assert validate_file_path(path) == path

    too_long = "a" * 253 + ".py"
    assert len(too_long) == 256
    with pytest.raises(ValueError, match="too long"):
        validate_file_path(too_long)


@pytest.mark.parametrize(
    "value",
    [
        "text/plain",
        "text/x-python",
        "application/json",
        "image/png",
        "application/vnd.oai.openapi+json",
    ],
)
def test_validate_content_type_ok(value: str) -> None:
    assert validate_content_type(value) == value


@pytest.mark.parametrize(
    "value,expected",
    [
        ("text/plain; charset=utf-8", "text/plain"),
        ("text/plain ; charset=utf-8", "text/plain"),
        ("text/plain;", "text/plain"),
        ("application/json; charset=utf-8; boundary=abc123", "application/json"),
    ],
)
def test_validate_content_type_accepts_parameters(value: str, expected: str) -> None:
    assert validate_content_type(value) == expected


def test_validate_content_type_strips_whitespace():
    assert validate_content_type("  text/plain  ") == "text/plain"


@pytest.mark.parametrize(
    "value",
    [
        "not-a-mime-type",
        "text\\plain",
        "text/",
        "/plain",
        "",
    ],
)
def test_validate_content_type_rejects_invalid(value: object) -> None:
    with pytest.raises(ValueError, match="Invalid content_type"):
        validate_content_type(value)


@pytest.mark.parametrize(
    "value",
    [
        "not-a-mime-type; charset=utf-8",
        "text\\plain; charset=utf-8",
        "text/; charset=utf-8",
        "/plain; charset=utf-8",
        "; charset=utf-8",
    ],
)
def test_validate_content_type_rejects_invalid_with_parameters(value: str) -> None:
    with pytest.raises(ValueError, match="Invalid content_type"):
        validate_content_type(value)
