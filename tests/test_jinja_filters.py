from markupsafe import Markup
from app.jinja_filters import bold


def test_bold_converts_double_asterisks():
    result = bold("This is **bold** text")
    assert str(result) == "This is <strong>bold</strong> text"
    assert isinstance(result, Markup)


def test_bold_escapes_html_preventing_xss():
    raw = "<script>alert('xss')</script> and **safe bold**"
    result = bold(raw)
    assert "<script>" not in str(result)
    assert "&lt;script&gt;alert(&#39;xss&#39;)&lt;/script&gt;" in str(result)
    assert "<strong>safe bold</strong>" in str(result)


def test_bold_multiple_occurrences():
    raw = "**One** and **Two** and **Three**"
    result = bold(raw)
    assert str(result) == "<strong>One</strong> and <strong>Two</strong> and <strong>Three</strong>"


def test_bold_unmatched_asterisks():
    raw = "This is **unmatched asterisk text"
    result = bold(raw)
    assert str(result) == "This is **unmatched asterisk text"


def test_bold_empty_and_non_string():
    assert str(bold("")) == ""
    assert str(bold(12345)) == "12345"
