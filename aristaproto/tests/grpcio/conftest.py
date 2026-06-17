from __future__ import annotations

import pytest

from tests.grpcio.fixtures import make_generated_style_base
from tests.util import requires_grpcio  # noqa: F401


@pytest.fixture
def grpcio_test_base(requires_grpcio):
    return make_generated_style_base()
