from dataclasses import dataclass

import pytest

import aristaproto


def test_oneof_pattern_matching():
    @dataclass
    class Sub(aristaproto.Message):
        val: int = aristaproto.int32_field(1)

    @dataclass
    class Foo(aristaproto.Message):
        bar: int = aristaproto.int32_field(1, group="group1")
        baz: str = aristaproto.string_field(2, group="group1")
        sub: Sub = aristaproto.message_field(3, group="group2")
        abc: str = aristaproto.string_field(4, group="group2")

    foo = Foo(baz="test1", abc="test2")

    # Test group1: Check if we can access baz (should be set) vs bar (should not be accessible)
    # Pattern matching would check if foo matches Foo(bar=_) first, then Foo(baz=v)
    # Since bar is not the active oneof field, accessing it raises AttributeError
    # So we check if baz is accessible and has the right value
    try:
        # Try to access bar - should raise AttributeError since baz is set
        _ = foo.bar
        pytest.fail("Matched 'bar' instead of 'baz'")
    except AttributeError:
        # Expected - bar is not set in the oneof group
        pass

    # Now check baz is accessible and has correct value
    try:
        v = foo.baz
        assert v == "test1"
    except AttributeError:
        pytest.fail("Matched neither 'bar' nor 'baz'")

    # Test group2: Check if we can access abc (should be set) vs sub (should not be accessible)
    try:
        # Try to access sub - should raise AttributeError since abc is set
        _ = foo.sub
        pytest.fail("Matched 'sub' instead of 'abc'")
    except AttributeError:
        # Expected - sub is not set in the oneof group
        pass

    # Now check abc is accessible and has correct value
    try:
        v = foo.abc
        assert v == "test2"
    except AttributeError:
        pytest.fail("Matched neither 'sub' nor 'abc'")

    # Set sub, which should make it the active field and abc inaccessible
    foo.sub = Sub(val=1)

    # Test group2 again: Now sub should be accessible and abc should not be
    try:
        # Check if sub is set and has the right nested value
        if isinstance(foo.sub, Sub) and foo.sub.val == 1:
            v = foo.sub.val
            assert v == 1
        else:
            pytest.fail("Matched neither 'sub' nor 'abc'")
    except AttributeError:
        pytest.fail("Matched neither 'sub' nor 'abc'")

    # Now abc should raise AttributeError
    try:
        _ = foo.abc
        pytest.fail("Matched 'abc' instead of 'sub'")
    except AttributeError:
        # Expected - abc is no longer the active field in group2
        pass
