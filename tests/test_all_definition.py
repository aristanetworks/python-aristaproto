def test_all_definition():
    """
    Check that a compiled module defines __all__ with the right value.

    These modules have been chosen since they contain messages, services and enums.
    """
    from tests.output_aristaproto import enum, service

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
