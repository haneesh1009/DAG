"""Parse Liberty Boolean expressions without evaluation or simplification.

Preserving syntactic support avoids dropping dependencies through algebraic
simplification. Whitespace adjacency is Liberty's implicit AND operator.
"""
import re

from .errors import BuildError

TOKEN = re.compile(r"\s*(?:(?P<name>[A-Za-z_][A-Za-z0-9_$]*(?:\[[0-9]+\])?)|(?P<op>[01!~'&*+|^()]))")


def parse(expression):
    text = str(expression).strip()
    tokens = []
    pos = 0
    while pos < len(text):
        match = TOKEN.match(text, pos)
        if not match:
            raise BuildError("UNSUPPORTED_FUNCTION", f"Unsupported Boolean expression: {text!r}")
        tokens.append(match.group("name") or match.group("op"))
        pos = match.end()
    index = 0

    def peek():
        return tokens[index] if index < len(tokens) else None

    def take():
        nonlocal index
        token = peek()
        index += 1
        return token

    def atom():
        token = take()
        if token in ("!", "~"):
            node = ("not", atom())
        elif token == "(":
            node = expr(0)
            if take() != ")":
                raise ValueError("missing closing parenthesis")
        elif token in ("0", "1"):
            node = ("constant", token)
        elif token and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_$]*(?:\[[0-9]+\])?", token):
            node = ("name", token)
        else:
            raise ValueError("expected operand")
        while peek() == "'":
            take()
            node = ("not", node)
        return node

    precedence = {"|": 1, "+": 1, "^": 2, "&": 3, "*": 3}

    def expr(minimum):
        left = atom()
        while peek() is not None and peek() != ")":
            token = peek()
            implicit = token not in precedence
            level = 3 if implicit else precedence[token]
            if level < minimum:
                break
            if not implicit:
                take()
            right = expr(level + 1)
            left = ("and" if implicit else token, left, right)
        return left

    try:
        tree = expr(0)
        if index != len(tokens):
            raise ValueError("trailing tokens")
        return tree
    except (ValueError, RecursionError) as error:
        raise BuildError("UNSUPPORTED_FUNCTION", f"Invalid Boolean expression {text!r}: {error}") from error


def support(tree):
    if tree[0] == "name":
        return {tree[1]}
    if tree[0] == "constant":
        return set()
    result = set()
    for child in tree[1:]:
        result.update(support(child))
    return result


def literal(tree):
    """Return the variable for a possibly inverted literal, otherwise None."""
    while tree[0] == "not":
        tree = tree[1]
    return tree[1] if tree[0] == "name" else None
