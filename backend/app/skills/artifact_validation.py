"""Check generated HTML against the preview's execution constraints."""

import re
from html.parser import HTMLParser


class PreviewHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.scripts = []
        self.in_script = False
        self.issues = set()

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "script":
            self.in_script = True
            if attributes.get("src"):
                self.issues.add("Replace external scripts with inline JavaScript; external assets are blocked.")
        if tag == "link" and "stylesheet" in (attributes.get("rel") or "").lower():
            self.issues.add("Replace linked stylesheets with inline CSS; external assets are blocked.")
        self.scripts.extend(value for name, value in attrs if name.startswith("on") and value)

    def handle_data(self, data):
        if self.in_script:
            self.scripts.append(data)

    def handle_endtag(self, tag):
        if tag == "script":
            self.in_script = False


def preview_issues(artifact):
    if artifact.language != "html":
        return []
    document = PreviewHTML()
    document.feed(artifact.content)
    document.close()
    if document.in_script:
        document.issues.add("Complete the script and close its script tag.")
    scripts = "\n".join(document.scripts)
    if re.search(r"\beval\s*\(|\b(?:new\s+)?Function\s*\(", scripts):
        document.issues.add("Remove eval and Function constructors. Use explicit arithmetic or a small expression parser.")
    if re.search(r"\b(?:localStorage|sessionStorage|indexedDB)\b", scripts):
        document.issues.add("Use in-memory state; browser storage is unavailable in the isolated preview.")
    return sorted(document.issues)
