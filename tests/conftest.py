import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--integration",
        action="store_true",
        default=False,
        help="Run integration tests (requires live Wikimedia network access)",
    )
    parser.addoption(
        "--docker",
        action="store_true",
        default=False,
        help="Run Docker tests (requires Docker daemon)",
    )


def pytest_collection_modifyitems(config, items):
    skip_integration = pytest.mark.skip(reason="pass --integration to run")
    skip_docker = pytest.mark.skip(reason="pass --docker to run")

    for item in items:
        if "integration" in item.keywords and not config.getoption("--integration"):
            item.add_marker(skip_integration)
        if "docker" in item.keywords and not config.getoption("--docker"):
            item.add_marker(skip_docker)
