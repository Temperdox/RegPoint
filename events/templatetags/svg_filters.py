from base64 import b64encode

from django import template

register = template.Library()


@register.filter
def svg_to_data_uri(svg_markup):
    """Encode an SVG string as a base64 data URI.

    Rendering via <img src="data:image/svg+xml;base64,..."> forces the browser
    to treat the SVG as an opaque image resource, which disables scripting and
    external references inside it. This eliminates the XSS surface that |safe
    would expose when the caller cannot prove the markup is static.
    """
    if not svg_markup:
        return ""
    if isinstance(svg_markup, str):
        svg_bytes = svg_markup.encode("utf-8")
    else:
        svg_bytes = bytes(svg_markup)
    encoded = b64encode(svg_bytes).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"
