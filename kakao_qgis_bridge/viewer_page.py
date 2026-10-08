"""Assemble packaged viewer scripts for both dock and external-browser HTML."""

import re

VIEWER_SCRIPTS = {
    "__VIEWER_SEARCH_SCRIPT__": "viewer_search.js",
    "__VIEWER_GUIDANCE_SCRIPT__": "viewer_guidance.js",
    "__VIEWER_HISTORY_SCRIPT__": "viewer_history.js",
    "__VIEWER_ROUTE_INPUT_SCRIPT__": "viewer_route_input.js",
}


def load_viewer_template(plugin_dir):
    web_dir = plugin_dir / "web"
    html = (web_dir / "kakao_viewer.html").read_text(encoding="utf-8")
    # Replace all markers in one pass: inserted script text is never templated.
    pattern = "|".join(re.escape(marker) for marker in VIEWER_SCRIPTS)
    return re.sub(
        pattern,
        lambda match: (web_dir / VIEWER_SCRIPTS[match.group()]).read_text(encoding="utf-8"),
        html,
    )
