import importlib

import pytest


@pytest.mark.parametrize(
    "output_package",
    ["tests.output_aristaproto", "tests.output_aristaproto_grpcio"],
    ids=["grpclib", "grpcio"],
)
def test_all_definition(output_package):
    """
    Check that a compiled module defines __all__ with the right value.

    These modules have been chosen since they contain messages, services and enums.
    """
    enum = importlib.import_module(f"{output_package}.enum")
    service = importlib.import_module(f"{output_package}.service")

    assert service.__all__ == (
        "ThingType",
        "DoThingRequest",
        "DoThingResponse",
        "GetThingRequest",
        "GetThingResponse",
        "TestStub",
        "TestBase",
    )
    assert enum.__all__ == ("Choice", "ArithmeticOperator", "Test")
