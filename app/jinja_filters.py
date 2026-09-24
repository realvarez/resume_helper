"""Custom Jinja2 filters shared by the web UI and the PDF renderer."""
import re

from markupsafe import Markup, escape

_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")


def bold(value: object) -> Markup:
    """Render **text** markers as <strong>text</strong>; escapes HTML first."""
    return Markup(_BOLD_RE.sub(r"<strong>\1</strong>", str(escape(value))))
