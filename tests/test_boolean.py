import pytest
from netlist_dag.boolean import parse, support, literal
from netlist_dag.errors import BuildError


@pytest.mark.parametrize("expression,expected", [
    ("(!S A) + (S B)", {"A", "B", "S"}), ("A' B + C", {"A", "B", "C"}),
    ("1", set()), ("!0", set()), ("A ^ A", {"A"}), ("A[3] & B", {"A[3]", "B"}),
])
def test_dependencies(expression, expected):
    assert support(parse(expression)) == expected


@pytest.mark.parametrize("expression", ["", "A &", "(A", "A)", "A ? B : C", "A + * B", "2", "A;foo", "()"])
def test_invalid(expression):
    with pytest.raises(BuildError):
        parse(expression)


def test_literal():
    assert literal(parse("!CLK")) == "CLK"
    assert literal(parse("A+B")) is None
