import copy
import os
import sys

import pytest


# Change in aristaproto fork - moved from test_input.py to conftest.py.
# Force pure-python implementation instead of C++, otherwise imports
# break things because we can't properly reset the symbol database.
os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"


def pytest_addoption(parser):
    parser.addoption(
        "--repeat", type=int, default=1, help="repeat the operation multiple times"
    )


@pytest.fixture(scope="session")
def repeat(request):
    return request.config.getoption("repeat")


@pytest.fixture
def reset_sys_path():
    original = copy.deepcopy(sys.path)
    yield
    sys.path = original
