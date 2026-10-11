from app.tools.file_filter import RepositoryFileFilter


def test_file_filter_ignored_directories():
    file_filter = RepositoryFileFilter()

    assert file_filter.is_ignored_path("node_modules/express/index.js") is True
    assert file_filter.is_ignored_path("venv/lib/site-packages/pkg.py") is True
    assert file_filter.is_ignored_path(".git/config") is True
    assert file_filter.is_ignored_path("app/main.py") is False


def test_file_filter_ignored_extensions():
    file_filter = RepositoryFileFilter()

    assert file_filter.is_ignored_path("assets/logo.png") is True
    assert file_filter.is_ignored_path("bundle.min.js") is True
    assert file_filter.is_ignored_path("package-lock.json") is False  # json extension not in ignored, checked by language/analyzable


def test_file_filter_analyzable():
    file_filter = RepositoryFileFilter(max_file_size_bytes=1000)

    ok, reason = file_filter.is_analyzable("src/app.py", size=500)
    assert ok is True
    assert reason == "analyzable"

    ok, reason = file_filter.is_analyzable("src/app.py", size=2000)
    assert ok is False
    assert "file_size_exceeds_limit" in reason

    ok, reason = file_filter.is_analyzable("docs/readme.txt", size=100)
    assert ok is False
    assert reason == "unsupported_language"
