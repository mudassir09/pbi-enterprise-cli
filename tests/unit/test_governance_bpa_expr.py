"""Unit tests for the safe BPA expression parser/evaluator (bpa_expr)."""

from __future__ import annotations

import pytest

from pbi_cli.governance.bpa_expr import (
    BpaContext,
    BpaUnsupported,
    compile_expression,
    evaluate_expression,
)


def col(**props: object) -> BpaContext:
    return BpaContext(props)


class TestLiteralsAndOperators:
    def test_string_equality_both_operators(self) -> None:
        assert evaluate_expression('DataType = "Double"', col(DataType="Double"))
        assert evaluate_expression('DataType == "Double"', col(DataType="Double"))

    def test_numeric_comparison(self) -> None:
        assert evaluate_expression("Length > 5", col(Length=10))
        assert not evaluate_expression("Length > 5", col(Length=2))
        assert evaluate_expression("Length >= 2", col(Length=2))
        assert evaluate_expression("Length <= 2", col(Length=2))

    def test_and_or_precedence(self) -> None:
        ctx = col(A="x", B="y", C="z")
        # A=="x" || (B=="no" && C=="no") -> True
        assert evaluate_expression('A == "x" || B == "no" && C == "no"', ctx)
        assert not evaluate_expression('A == "no" && B == "y"', ctx)

    def test_in_list(self) -> None:
        assert evaluate_expression('DataType in {"Double", "Decimal"}', col(DataType="Double"))
        assert not evaluate_expression('DataType in {"Double", "Decimal"}', col(DataType="Int64"))

    def test_case_insensitive_property_lookup(self) -> None:
        assert evaluate_expression("datatype == \"Double\"", col(DataType="Double"))


class TestStringMethods:
    def test_startswith_endswith(self) -> None:
        assert evaluate_expression('Name.StartsWith("_")', col(Name="_x"))
        assert evaluate_expression('Name.EndsWith("Key")', col(Name="ProductKey"))

    def test_contains_toupper_tolower(self) -> None:
        assert evaluate_expression('Name.Contains("rev")', col(Name="prevent"))
        assert evaluate_expression('Name.ToUpper() == "ABC"', col(Name="abc"))
        assert evaluate_expression('Name.ToLower() == "abc"', col(Name="ABC"))

    def test_length_property_and_method_chain(self) -> None:
        assert evaluate_expression("Name.Length == 3", col(Name="abc"))


class TestRegex:
    def test_ismatch(self) -> None:
        assert evaluate_expression('RegEx.IsMatch(Name, "^[A-Z]")', col(Name="Total"))
        assert not evaluate_expression('RegEx.IsMatch(Name, "^[A-Z]")', col(Name="total"))

    def test_bad_regex_is_unsupported(self) -> None:
        with pytest.raises(BpaUnsupported):
            evaluate_expression('RegEx.IsMatch(Name, "(")', col(Name="x"))

    def test_leading_inline_flag(self) -> None:
        assert evaluate_expression(r'RegEx.IsMatch(Expression, "(?i)IFERROR")',
                                   col(Expression="iferror(1,2)"))

    def test_mid_pattern_inline_flag(self) -> None:
        # .NET allows (?i) mid-pattern; Python errors unless we relocate it.
        ctx = col(Expression="CALCULATE( x, filter(")
        assert evaluate_expression(
            r'RegEx.IsMatch(Expression, "CALCULATE\s*\(\s*[^,]+,\s*(?i)FILTER")', ctx
        )

    def test_backslash_metachars_preserved(self) -> None:
        # The literal "\t" must stay a regex tab metachar, not become a real tab,
        # and "\d" must stay a digit class. Regression for unicode_escape misuse.
        assert evaluate_expression(r'RegEx.IsMatch(Expression, "a\d+b")',
                                   col(Expression="a123b"))
        assert not evaluate_expression(r'RegEx.IsMatch(Expression, "a\tb")',
                                       col(Expression="a b"))
        assert evaluate_expression(r'RegEx.IsMatch(Expression, "a\tb")',
                                   col(Expression="a\tb"))


class TestEnumConstants:
    def test_datatype_enum_member(self) -> None:
        assert evaluate_expression("DataType != DataType.Int64", col(DataType="Double"))
        assert not evaluate_expression("DataType != DataType.Int64", col(DataType="Int64"))

    def test_enum_equality(self) -> None:
        assert evaluate_expression(
            "CrossFilteringBehavior == CrossFilteringBehavior.BothDirections",
            col(CrossFilteringBehavior="BothDirections"),
        )


class TestMoreStringMethods:
    def test_substring(self) -> None:
        assert evaluate_expression('Name.Substring(0, 3) == "abc"', col(Name="abcdef"))
        assert evaluate_expression('Name.Substring(3) == "def"', col(Name="abcdef"))

    def test_tostring(self) -> None:
        assert evaluate_expression('Name.ToString() == "x"', col(Name="x"))


class TestAnnotationsAndConvert:
    def test_get_annotation_with_convert(self) -> None:
        ctx = BpaContext({"Name": "Sales"}, annotations={"Vertipaq_RowCount": "30000000"})
        assert evaluate_expression(
            'Convert.ToInt64(GetAnnotation("Vertipaq_RowCount")) > 25000000', ctx
        )
        ctx2 = BpaContext({"Name": "Small"}, annotations={"Vertipaq_RowCount": "100"})
        assert not evaluate_expression(
            'Convert.ToInt64(GetAnnotation("Vertipaq_RowCount")) > 25000000', ctx2
        )

    def test_missing_annotation_defaults_to_zero_when_collected(self) -> None:
        # Collected (dict present) but this object lacks the annotation -> "0".
        ctx = BpaContext({"Name": "C"}, annotations={})
        assert not evaluate_expression(
            'Convert.ToInt32(GetAnnotation("DateTimeWithHourMinSec")) > 0', ctx
        )

    def test_annotation_without_stats_is_unsupported(self) -> None:
        # No stats collected (annotations is None) -> rule must skip, not guess.
        ctx = BpaContext({"Name": "C"})
        with pytest.raises(BpaUnsupported):
            evaluate_expression('Convert.ToInt64(GetAnnotation("Vertipaq_RowCount")) > 0', ctx)

    def test_convert_casts(self) -> None:
        ctx = BpaContext({"Card": "5"}, annotations={})
        assert evaluate_expression("Convert.ToDouble(Card) == 5", ctx)
        assert evaluate_expression('Convert.ToString(Card) == "5"', ctx)

    def test_char_function(self) -> None:
        # SPECIAL_CHARS_IN_OBJECT_NAMES uses char(9) (tab) etc.
        assert evaluate_expression("Name.IndexOf(char(9)) > -1", col(Name="a\tb"))
        assert not evaluate_expression("Name.IndexOf(char(9)) > -1", col(Name="ab"))

    def test_unknown_function_is_unsupported(self) -> None:
        with pytest.raises(BpaUnsupported):
            evaluate_expression("Frobnicate(Name)", col(Name="x"))


class TestStringStaticHelpers:
    def test_is_null_or_whitespace(self) -> None:
        assert evaluate_expression("string.IsNullOrWhitespace(Description)", col(Description=""))
        assert evaluate_expression("string.IsNullOrWhitespace(Description)", col(Description="   "))
        assert not evaluate_expression(
            "string.IsNullOrWhitespace(Description)", col(Description="doc")
        )

    def test_is_null_or_empty(self) -> None:
        assert evaluate_expression("string.IsNullOrEmpty(SourceColumn)", col(SourceColumn=""))
        assert not evaluate_expression("string.IsNullOrEmpty(SourceColumn)", col(SourceColumn="x"))


class TestIndexer:
    def _table(self, *parts: BpaContext) -> BpaContext:
        return BpaContext({"Name": "T"}, {"Partitions": list(parts)})

    def test_first_element(self) -> None:
        t = self._table(col(Name="P1"), col(Name="P2"))
        assert evaluate_expression('Partitions[0].Name == "P1"', t)
        assert evaluate_expression('Partitions[1].Name == "P2"', t)

    def test_partition_name_should_match_table_pattern(self) -> None:
        # The real rule: Partitions.Count = 1 and Partitions[0].Name <> Name
        mismatch = BpaContext({"Name": "Sales"}, {"Partitions": [col(Name="Partition 1")]})
        assert evaluate_expression(
            "Partitions.Count = 1 and Partitions[0].Name <> Name", mismatch
        )
        match = BpaContext({"Name": "Sales"}, {"Partitions": [col(Name="Sales")]})
        assert not evaluate_expression(
            "Partitions.Count = 1 and Partitions[0].Name <> Name", match
        )

    def test_out_of_range_is_unsupported(self) -> None:
        with pytest.raises(BpaUnsupported):
            evaluate_expression("Partitions[5].Name", self._table(col(Name="P1")))


class TestCharMathAndArrays:
    def test_tochararray_and_char_iscontrol(self) -> None:
        # Real rule: Name.ToCharArray().Any(char.IsControl(it) and !char.IsWhiteSpace(it))
        bad = col(Name="ok\x07bad")  # bell char = control, not whitespace
        good = col(Name="all good")
        expr = "Name.ToCharArray().Any(char.IsControl(it) and !char.IsWhiteSpace(it))"
        assert evaluate_expression(expr, bad)
        assert not evaluate_expression(expr, good)

    def test_math_max(self) -> None:
        assert evaluate_expression("Math.Max(N, 1) == 5", col(N=5))
        assert evaluate_expression("Math.Max(N, 1) == 1", col(N=0))


class TestDoubledQuoteStrings:
    def test_doubled_double_quote_escape(self) -> None:
        # C# verbatim-style "" escape inside a double-quoted literal.
        assert evaluate_expression('Query.Contains("[Query=""SELECT")',
                                   col(Query='x [Query="SELECT * ]'))
        assert not evaluate_expression('Query.Contains("[Query=""SELECT")',
                                       col(Query="no match"))


class TestClosureSemantics:
    def test_outerit_is_rule_object_at_first_level(self) -> None:
        # Model.AllMeasures.Any(... = outerit.Expression ... and it <> outerit)
        m1 = BpaContext({"Name": "A", "Expression": "SUM(x)", "ObjectType": "Measure"})
        m2 = BpaContext({"Name": "B", "Expression": "SUM(x)", "ObjectType": "Measure"})
        m3 = BpaContext({"Name": "C", "Expression": "SUM(y)", "ObjectType": "Measure"})
        model = BpaContext({}, {"AllMeasures": [m1, m2, m3]})
        for m in (m1, m2, m3):
            m.set_prop("Model", model)
        expr = "Model.AllMeasures.Any(Expression == outerit.Expression and it <> outerit)"
        # m1 duplicates m2 -> flagged; m3 is unique -> not
        assert evaluate_expression(expr, m1.bind_closures({"current": m1}))
        assert not evaluate_expression(expr, m3.bind_closures({"current": m3}))

    def test_allmeasures_filters_by_object_type(self) -> None:
        meas = BpaContext({"Name": "M", "ObjectType": "Measure"})
        c = BpaContext({"Name": "C", "ObjectType": "Column"})
        ctx = BpaContext({}, {"Items": [meas, c]})
        assert evaluate_expression("Items.AllMeasures.Count == 1", ctx)
        assert evaluate_expression("Items.AllColumns.Count == 1", ctx)


class TestCollections:
    def _table(self, *cols: BpaContext) -> BpaContext:
        return BpaContext({"Name": "T"}, {"Columns": list(cols)})

    def test_any(self) -> None:
        t = self._table(col(DataType="Double"), col(DataType="Int64"))
        assert evaluate_expression('Columns.Any(DataType == "Double")', t)
        assert not evaluate_expression('Columns.Any(DataType == "String")', t)

    def test_any_no_predicate_is_nonempty(self) -> None:
        assert evaluate_expression("Columns.Any()", self._table(col(Name="a")))
        assert not evaluate_expression("Columns.Any()", self._table())

    def test_all(self) -> None:
        t = self._table(col(IsHidden=True), col(IsHidden=True))
        assert evaluate_expression("Columns.All(IsHidden)", t)
        t2 = self._table(col(IsHidden=True), col(IsHidden=False))
        assert not evaluate_expression("Columns.All(IsHidden)", t2)

    def test_count_property_and_method(self) -> None:
        t = self._table(col(Name="a"), col(Name="b"))
        assert evaluate_expression("Columns.Count == 2", t)
        assert evaluate_expression("Columns.Count() == 2", t)

    def test_where_then_count(self) -> None:
        t = self._table(col(DataType="Double"), col(DataType="Int64"), col(DataType="Double"))
        assert evaluate_expression('Columns.Where(DataType == "Double").Count == 2', t)


class TestSafetyAndHonesty:
    def test_no_eval_arbitrary_code(self) -> None:
        # Must not execute Python; treat as unparseable/unsupported, never run it.
        with pytest.raises(BpaUnsupported):
            evaluate_expression('__import__("os").system("echo hi")', col(Name="x"))

    def test_unknown_property_raises(self) -> None:
        with pytest.raises(BpaUnsupported):
            evaluate_expression("IsKey", col(Name="x"))

    def test_empty_expression_raises(self) -> None:
        with pytest.raises(BpaUnsupported):
            compile_expression("   ")

    def test_unbalanced_parens_raise(self) -> None:
        with pytest.raises(BpaUnsupported):
            compile_expression('(DataType == "Double"')

    def test_compile_once_eval_many(self) -> None:
        node = compile_expression('DataType == "Double"')
        from pbi_cli.governance.bpa_expr import evaluate

        assert evaluate(node, col(DataType="Double"))
        assert not evaluate(node, col(DataType="Int64"))
