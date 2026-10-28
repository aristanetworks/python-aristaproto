import pytest

from tests.output_aristaproto.namespace_map_builtin_types import Test
from tests.output_aristaproto_pydantic.namespace_map_builtin_types import (
    Test as TestPyd,
)


@pytest.mark.parametrize("message_type", [Test, TestPyd])
def test_map_builtin_collision_round_trip(message_type):
    message = message_type(
        before={"first": "value"},
        str=7,
        after={"second": "value"},
        builtins=8,
    )

    decoded = message_type.FromString(bytes(message))

    assert decoded == message
    assert decoded.before == {"first": "value"}
    assert decoded.after == {"second": "value"}
    assert decoded.str == 7
    assert decoded.builtins == 8
