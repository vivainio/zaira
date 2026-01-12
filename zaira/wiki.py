"""Confluence API commands."""

import argparse
import re
import sys

import requests
from requests.auth import HTTPBasicAuth

from zaira.jira_client import load_credentials, get_server_from_config


def get_confluence_auth() -> tuple[str, HTTPBasicAuth]:
    """Get Confluence base URL and auth.

    Returns:
        Tuple of (base_url, auth)
    """
    creds = load_credentials()
    server = get_server_from_config()

    if not server or not creds.get("email") or not creds.get("api_token"):
        print("Error: Credentials not configured", file=sys.stderr)
        print("Run 'zaira init' to set up credentials.", file=sys.stderr)
        sys.exit(1)

    base_url = server + "/wiki/rest/api"
    auth = HTTPBasicAuth(creds["email"], creds["api_token"])
    return base_url, auth


def parse_page_id(page_ref: str) -> str:
    """Parse page ID from URL or return as-is if numeric.

    Args:
        page_ref: Page ID or Confluence URL

    Returns:
        Page ID string
    """
    # If it's just a number, return it
    if page_ref.isdigit():
        return page_ref

    # Try to extract from URL patterns:
    # https://site.atlassian.net/wiki/spaces/SPACE/pages/123456/Title
    # https://site.atlassian.net/wiki/pages/viewpage.action?pageId=123456
    match = re.search(r"/pages/(\d+)", page_ref)
    if match:
        return match.group(1)

    match = re.search(r"pageId=(\d+)", page_ref)
    if match:
        return match.group(1)

    # Assume it's already an ID
    return page_ref


def get_command(args: argparse.Namespace) -> None:
    """Get a Confluence page by ID or URL."""
    base_url, auth = get_confluence_auth()
    page_id = parse_page_id(args.page)

    r = requests.get(
        f"{base_url}/content/{page_id}",
        params={"expand": "body.storage,version,space"},
        auth=auth,
    )

    if not r.ok:
        print(f"Error: {r.status_code} - {r.reason}", file=sys.stderr)
        if r.status_code == 404:
            print(f"Page not found: {page_id}", file=sys.stderr)
        else:
            print(r.text, file=sys.stderr)
        sys.exit(1)

    page = r.json()
    title = page["title"]
    space_key = page["space"]["key"]
    space_name = page["space"]["name"]
    version = page["version"]["number"]
    body_html = page["body"]["storage"]["value"]

    if args.format == "json":
        import json
        print(json.dumps(page, indent=2))
    elif args.format == "html":
        print(f"Title: {title}")
        print(f"Space: {space_name} ({space_key})")
        print(f"Version: {version}")
        print(f"Page ID: {page_id}")
        print()
        print(body_html)
    else:
        # Default: md - convert HTML to markdown
        print(f"Title: {title}")
        print(f"Space: {space_name} ({space_key})")
        print(f"Version: {version}")
        print(f"Page ID: {page_id}")
        print()
        from html.parser import HTMLParser

        class MarkdownExtractor(HTMLParser):
            HEADER_LEVELS = {
                "h1": "#", "h2": "##", "h3": "###",
                "h4": "####", "h5": "#####", "h6": "######",
            }

            def __init__(self):
                super().__init__()
                self.text = []
                self.in_li = False
                self.in_code = False

            def handle_starttag(self, tag, attrs):
                if tag == "br":
                    self.text.append("\n")
                elif tag in self.HEADER_LEVELS:
                    self.text.append(f"\n{self.HEADER_LEVELS[tag]} ")
                elif tag == "li":
                    self.text.append("- ")
                    self.in_li = True
                elif tag in {"code", "pre"}:
                    self.text.append("`")
                    self.in_code = True
                elif tag == "strong" or tag == "b":
                    self.text.append("**")
                elif tag == "em" or tag == "i":
                    self.text.append("*")
                elif tag == "hr":
                    self.text.append("\n---\n")

            def handle_endtag(self, tag):
                if tag in self.HEADER_LEVELS:
                    self.text.append("\n")
                elif tag == "li":
                    self.text.append("\n")
                    self.in_li = False
                elif tag in {"p", "div", "tr"}:
                    self.text.append("\n")
                elif tag in {"code", "pre"}:
                    self.text.append("`")
                    self.in_code = False
                elif tag == "strong" or tag == "b":
                    self.text.append("**")
                elif tag == "em" or tag == "i":
                    self.text.append("*")
                elif tag in {"ul", "ol", "table", "blockquote"}:
                    self.text.append("\n")

            def handle_data(self, data):
                self.text.append(data)

        extractor = MarkdownExtractor()
        extractor.feed(body_html)
        # Collapse multiple newlines into max 2
        import re
        text = "".join(extractor.text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        print(text.strip())


def wiki_command(args: argparse.Namespace) -> None:
    """Handle wiki subcommand."""
    if hasattr(args, "wiki_func"):
        args.wiki_func(args)
    else:
        print("Usage: zaira wiki <subcommand>")
        print("Subcommands: get")
        sys.exit(1)
