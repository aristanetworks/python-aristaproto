import inspect

from tests.output_aristaproto.regression_108 import Test


def test_multiline_comment_indentation_is_preserved():
    assert (
        inspect.getdoc(Test)
        == "Summary:\n  keeps one level of indentation\n    keeps nested indentation too"
    )
