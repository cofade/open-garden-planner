"""Unit tests for the safe parametric expression evaluator (US-C4)."""

import math

import pytest

from open_garden_planner.core.parametric_eval import safe_eval


class TestArithmetic:
    def test_literals_and_precedence(self) -> None:
        assert safe_eval("1 + 2 * 3") == 7.0
        assert safe_eval("(1 + 2) * 3") == 9.0
        assert safe_eval("2 ** 3") == 8.0
        assert safe_eval("7 % 3") == 1.0
        assert safe_eval("7 // 2") == 3.0
        assert safe_eval("-5 + 2") == -3.0

    def test_variables(self) -> None:
        assert safe_eval("W * i / rows", {"W": 100, "i": 2, "rows": 4}) == 50.0
        assert safe_eval("L", {"L": 200}) == 200.0

    def test_whitelisted_functions(self) -> None:
        assert safe_eval("max(L - 2*m, 0)", {"L": 10, "m": 8}) == 0.0
        assert safe_eval("min(3, 9)") == 3.0
        assert safe_eval("abs(-4)") == 4.0
        assert safe_eval("sqrt(9)") == 3.0
        assert safe_eval("floor(2.9)") == 2.0
        assert safe_eval("ceil(2.1)") == 3.0
        assert safe_eval("round(2.5)") == 2.0  # banker's rounding, fine

    def test_returns_float(self) -> None:
        assert isinstance(safe_eval("3"), float)


class TestRejections:
    @pytest.mark.parametrize(
        "expr",
        [
            "__import__('os').system('ls')",
            "os.system('x')",
            "(1).__class__",
            "x.attr",
            "[i for i in range(3)]",
            "lambda: 1",
            "open('f')",
            "print(1)",
            "1 if True else 2",
            "{1: 2}",
            "'a' + 'b'",
            "True",
        ],
    )
    def test_disallowed_constructs_raise(self, expr: str) -> None:
        with pytest.raises(ValueError):
            safe_eval(expr, {"x": 1})

    def test_unknown_variable_raises(self) -> None:
        with pytest.raises(ValueError):
            safe_eval("a + b", {"a": 1})

    def test_unknown_function_raises(self) -> None:
        with pytest.raises(ValueError):
            safe_eval("pow(2, 3)")

    def test_keyword_args_rejected(self) -> None:
        with pytest.raises(ValueError):
            safe_eval("round(2.5, ndigits=1)")

    def test_syntax_error_raises_valueerror(self) -> None:
        with pytest.raises(ValueError):
            safe_eval("1 +")

    def test_no_sqrt_of_negative_leaks(self) -> None:
        # math domain error surfaces (not a security issue, just confirm no crash type leak)
        with pytest.raises((ValueError,)):
            safe_eval("sqrt(-1)")
        assert math.isnan(float("nan"))  # sanity

    def test_deeply_nested_expression_raises_valueerror_not_recursionerror(self) -> None:
        # A long flat operator chain from untrusted JSON nests the AST deeply;
        # without the node cap the recursive evaluator blows the stack with
        # RecursionError (a RuntimeError, NOT a ValueError). The cap must reject
        # it as a plain ValueError so the failure surface stays bounded.
        bomb = "+".join(["1"] * 5000)
        with pytest.raises(ValueError):
            safe_eval(bomb)

    def test_node_cap_allows_real_formulas(self) -> None:
        # The cap must be comfortably above any legitimate coordinate formula.
        assert safe_eval("max(L - 2*margin, 0) + W*i/rows",
                         {"L": 200, "margin": 10, "W": 100, "i": 2, "rows": 4}) == 230.0
