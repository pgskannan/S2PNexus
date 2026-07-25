"""Root-level pytest configuration and compatibility patches."""

try:
    import _pytest.python as pytest_python

    if not hasattr(pytest_python.Package, "obj"):
        pytest_python.Package.obj = property(lambda self: None)
except Exception:
    pass
