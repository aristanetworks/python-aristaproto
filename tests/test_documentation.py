import ast
import importlib
import inspect

import pytest


def check(generated_doc: str, type: str) -> None:
    assert f"Documentation of {type} 1" in generated_doc
    assert "other line 1" in generated_doc
    assert f"Documentation of {type} 2" in generated_doc
    assert "other line 2" in generated_doc
    assert f"Documentation of {type} 3" in generated_doc


@pytest.mark.parametrize(
    "output_package",
    ["tests.output_aristaproto", "tests.output_aristaproto_grpcio"],
    ids=["grpclib", "grpcio"],
)
def test_documentation(output_package: str) -> None:
    module = importlib.import_module(f"{output_package}.documentation")
    Enum = module.Enum
    ServiceBase = module.ServiceBase
    ServiceStub = module.ServiceStub
    Test = module.Test
    Undocumented = module.Undocumented

    check(Test.__doc__, "message")

    source = inspect.getsource(Test)
    tree = ast.parse(source)
    check(tree.body[0].body[2].value.value, "field")

    check(Enum.__doc__, "enum")

    source = inspect.getsource(Enum)
    tree = ast.parse(source)
    check(tree.body[0].body[2].value.value, "variant")

    assert tree.body[0].body[3].targets[0].id == "Enum_Variant_Undocumented"
    assert len(tree.body[0].body) == 4

    check(ServiceBase.__doc__, "service")
    check(ServiceBase.get.__doc__, "method")
    assert ServiceBase.undocumented.__doc__ is None

    check(ServiceStub.__doc__, "service")
    check(ServiceStub.get.__doc__, "method")

    # Check comments are missing in undocumented objects
    assert ast.get_docstring(ast.parse(inspect.getsource(Undocumented))) is None
    assert ast.get_docstring(ast.parse(inspect.getsource(Enum))) is None
