"""Environment compatibility patches for local test execution."""

try:
    import _pytest.python as pytest_python

    if not hasattr(pytest_python.Package, "obj"):
        def _package_obj(self):
            return None

        pytest_python.Package.obj = property(_package_obj)
except Exception:
    pass
