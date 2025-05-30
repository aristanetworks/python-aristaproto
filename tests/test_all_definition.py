def test_all_definition():
    """
    Check that a compiled module defines __all__ with the right value.

    These modules have been chosen since they contain messages, services and enums.
    """
    import tests.output_aristaproto.enum as enum
    import tests.output_aristaproto.service as service

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
