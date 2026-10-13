import pytest

# Export every frozen-matrix requirement marker into JUnit testcase properties.
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    for marker in item.iter_markers(name="requirement"):
        if marker.args:
            report.user_properties.append(("requirement", str(marker.args[0])))
