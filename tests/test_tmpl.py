import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/init-math/scripts"))

from renderer.tmpl import TemplateError, render  # noqa: E402


class TestVars(unittest.TestCase):
    def test_plain_and_dotted(self):
        self.assertEqual(render("a {{x}} {{p.q}}", {"x": 1, "p": {"q": "z"}}), "a 1 z")

    def test_missing_is_error(self):
        with self.assertRaises(TemplateError):
            render("{{nope}}", {})

    def test_missing_dotted_is_error(self):
        with self.assertRaises(TemplateError):
            render("{{p.nope}}", {"p": {}})

    def test_bool_renders(self):
        self.assertEqual(render("{{t}}/{{f}}", {"t": True, "f": False}), "true/false")

    def test_list_interpolation_is_error(self):
        with self.assertRaises(TemplateError):
            render("{{xs}}", {"xs": [1]})

    def test_no_html_escaping(self):
        self.assertEqual(render("{{x}}", {"x": "<a & b>"}), "<a & b>")


class TestIf(unittest.TestCase):
    def test_if_else(self):
        t = "{{#if a}}yes{{else}}no{{/if}}"
        self.assertEqual(render(t, {"a": True}), "yes")
        self.assertEqual(render(t, {"a": False}), "no")

    def test_falsy_values(self):
        for v in (None, False, "", [], {}, 0):
            self.assertEqual(render("{{#if a}}y{{/if}}", {"a": v}), "")

    def test_negation(self):
        self.assertEqual(render("{{#if !a}}y{{/if}}", {"a": []}), "y")

    def test_missing_in_if_is_error(self):
        with self.assertRaises(TemplateError):
            render("{{#if a}}y{{/if}}", {})

    def test_unclosed(self):
        with self.assertRaises(TemplateError):
            render("{{#if a}}y", {"a": 1})

    def test_mismatched(self):
        with self.assertRaises(TemplateError):
            render("{{#if a}}y{{/each}}", {"a": 1})


class TestEach(unittest.TestCase):
    def test_dict_items_in_scope(self):
        t = "{{#each xs}}{{n}}{{#if !@last}},{{/if}}{{/each}}"
        self.assertEqual(render(t, {"xs": [{"n": 1}, {"n": 2}]}), "1,2")

    def test_scalar_dot(self):
        self.assertEqual(render("{{#each xs}}[{{.}}]{{/each}}", {"xs": ["a", "b"]}), "[a][b]")

    def test_outer_scope_visible(self):
        t = "{{#each xs}}{{pre}}{{.}}{{/each}}"
        self.assertEqual(render(t, {"pre": "-", "xs": [1, 2]}), "-1-2")

    def test_index(self):
        self.assertEqual(render("{{#each xs}}{{@index}}{{/each}}", {"xs": [9, 9]}), "01")

    def test_non_list_is_error(self):
        with self.assertRaises(TemplateError):
            render("{{#each xs}}{{/each}}", {"xs": "ab"})


class TestStandaloneAndRaw(unittest.TestCase):
    def test_standalone_block_lines_removed(self):
        t = "a\n{{#if x}}\nb\n{{/if}}\nc\n"
        self.assertEqual(render(t, {"x": True}), "a\nb\nc\n")
        self.assertEqual(render(t, {"x": False}), "a\nc\n")

    def test_indented_standalone(self):
        t = "a\n  {{#each xs}}\n- {{.}}\n  {{/each}}\nz\n"
        self.assertEqual(render(t, {"xs": [1, 2]}), "a\n- 1\n- 2\nz\n")

    def test_var_line_not_standalone(self):
        self.assertEqual(render("{{x}}\n", {"x": "v"}), "v\n")

    def test_comment_dropped(self):
        self.assertEqual(render("a\n{{! note }}\nb\n", {}), "a\nb\n")

    def test_raw_verbatim(self):
        t = "{{{{raw}}}}\\frac{{a}}{b} {{x}}{{{{/raw}}}} {{x}}"
        self.assertEqual(render(t, {"x": 1}), "\\frac{{a}}{b} {{x}} 1")

    def test_unbalanced_raw(self):
        with self.assertRaises(TemplateError):
            render("{{{{raw}}}} x", {})


if __name__ == "__main__":
    unittest.main()
