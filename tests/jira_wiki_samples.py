"""Jira wiki markup samples from Atlassian's Text Formatting Notation reference.

Source: https://jira.atlassian.com/secure/WikiRendererHelpAction.jspa?section=all

Each sample is a (wiki_input, expected_markdown) tuple.
"""

# --- Headings ---
HEADINGS = [
    ("h1. Biggest heading", "# Biggest heading"),
    ("h2. Bigger heading", "## Bigger heading"),
    ("h3. Big heading", "### Big heading"),
    ("h4. Normal heading", "#### Normal heading"),
    ("h5. Small heading", "##### Small heading"),
    ("h6. Smallest heading", "###### Smallest heading"),
]

# --- Text Effects ---
TEXT_EFFECTS = [
    # Bold
    ("*strong*", "**strong**"),
    ("This is *bold* text", "This is **bold** text"),
    # Italic/emphasis
    ("_emphasis_", "*emphasis*"),
    ("This is _italic_ text", "This is *italic* text"),
    # Citation
    ("??citation??", "*citation*"),
    # Strikethrough
    ("-deleted-", "~~deleted~~"),
    ("This is -deleted- text", "This is ~~deleted~~ text"),
    # Inserted/underline (no markdown equivalent, map to italic)
    ("+inserted+", "*inserted*"),
    # Superscript
    ("^superscript^", "<sup>superscript</sup>"),
    ("E = mc^2^", "E = mc<sup>2</sup>"),
    # Subscript
    ("~subscript~", "<sub>subscript</sub>"),
    ("H~2~O", "H<sub>2</sub>O"),
    # Monospace / inline code
    ("{{monospaced}}", "`monospaced`"),
    ("Use {{println()}} here", "Use `println()` here"),
    # Inline code with underscores should be protected
    ("{{my_var_name}}", "`my_var_name`"),
    # Combined effects
    ("*bold* and _italic_", "**bold** and *italic*"),
    ("*bold with {{code}}*", "**bold with `code`**"),
]

# --- Color ---
COLOR = [
    ("{color:red}red text{color}", "red text"),
    ("{color:#0000ff}blue text{color}", "blue text"),
    ("Before {color:green}green{color} after", "Before green after"),
]

# --- Text Breaks ---
TEXT_BREAKS = [
    # Horizontal rule
    ("----", "---"),
    ("-----", "---"),
    # Em dash (---) and en dash (--)
    ("word---word", "word\u2014word"),
    ("word--word", "word\u2013word"),
    # Forced line break
    ("line one\\\\line two", "line one<br>line two"),
]

# --- Links ---
LINKS = [
    # Aliased link
    ("[Atlassian|https://atlassian.com]", "[Atlassian](https://atlassian.com)"),
    ("[click here|https://example.com]", "[click here](https://example.com)"),
    # Bare URL
    ("[https://example.com]", "https://example.com"),
    ("[http://example.com/path]", "http://example.com/path"),
    # User mention
    ("[~johndoe]", "@johndoe"),
    ("[~accountid:5b10a2844c20165700ede21g]", "@5b10a2844c20165700ede21g"),
    # Attachment link
    ("[^report.pdf]", "report.pdf"),
    # Mailto
    ("[mailto:user@example.com]", "[mailto:user@example.com]"),
]

# --- Images ---
IMAGES = [
    ("!image.png!", "![](image.png)"),
    ("!http://example.com/img.gif!", "![](http://example.com/img.gif)"),
    ("!image.jpg|thumbnail!", "![](image.jpg)"),
    ("!image.gif|align=right, vspace=4!", "![](image.gif)"),
    ("!image.png|width=500!", "![](image.png)"),
    ("!screenshot.png|width=800,alt=\"My screenshot\"!", "![](screenshot.png)"),
]

# --- Bullet Lists ---
BULLET_LISTS = [
    # Simple
    ("* item one\n* item two\n* item three", "- item one\n- item two\n- item three"),
    # Nested
    ("* item\n** nested\n** also nested\n* back", "- item\n  - nested\n  - also nested\n- back"),
    # Deep nesting
    ("* level 1\n** level 2\n*** level 3", "- level 1\n  - level 2\n    - level 3"),
    # Hyphen alternate style (Jira supports - as well)
    # Note: - is handled differently in our parser (as regular text + inline)
]

# --- Numbered Lists ---
NUMBERED_LISTS = [
    # Simple
    ("# first\n# second\n# third", "1. first\n1. second\n1. third"),
    # Nested
    ("# first\n## nested\n## also nested\n# second", "1. first\n  1. nested\n  1. also nested\n1. second"),
    # Deep nesting
    ("# level 1\n## level 2\n### level 3", "1. level 1\n  1. level 2\n    1. level 3"),
]

# --- Mixed Lists ---
MIXED_LISTS = [
    # Numbered inside bullet
    ("* bullet\n*# numbered under bullet", "- bullet\n  1. numbered under bullet"),
    # Bullet inside numbered
    ("# numbered\n#* bullet under number", "1. numbered\n  - bullet under number"),
]

# --- Blockquotes ---
BLOCKQUOTES = [
    # Single line bq.
    ("bq. Some block quoted text", "> Some block quoted text"),
    ("bq. A *bold* quote", "> A **bold** quote"),
    # Multi-line {quote}
    ("{quote}\nfirst line\nsecond line\n{quote}", "> first line\n> second line"),
    # Quote with formatting
    ("{quote}\nThis is *bold* in a quote\n{quote}", "> This is **bold** in a quote"),
]

# --- Tables ---
TABLES = [
    # Simple header + rows
    (
        "||heading 1||heading 2||heading 3||\n|col A1|col A2|col A3|\n|col B1|col B2|col B3|",
        "| heading 1 | heading 2 | heading 3 |\n|---|---|---|\n| col A1 | col A2 | col A3 |\n| col B1 | col B2 | col B3 |",
    ),
    # Table with formatting in cells
    (
        "||*Name*||*Age*||\n|Alice|30|\n|Bob|25|",
        "| **Name** | **Age** |\n|---|---|\n| Alice | 30 |\n| Bob | 25 |",
    ),
]

# --- Code Blocks ---
CODE_BLOCKS = [
    # With language
    ("{code:java}\npublic String getFoo() {\n    return foo;\n}\n{code}",
     "```java\npublic String getFoo() {\n    return foo;\n}\n```"),
    # Language= form
    ("{code:language=python}\ndef hello():\n    print('hi')\n{code}",
     "```python\ndef hello():\n    print('hi')\n```"),
    # Short language form
    ("{code:sql}\nSELECT * FROM table;\n{code}",
     "```sql\nSELECT * FROM table;\n```"),
    # No language
    ("{code}\nplain code\n{code}",
     "```\nplain code\n```"),
]

# --- Noformat ---
NOFORMAT = [
    # Block
    ("{noformat}\npreformatted text\nwith *no* formatting\n{noformat}",
     "```\npreformatted text\nwith *no* formatting\n```"),
    # Inline start
    ("{noformat}code on same line\n{noformat}",
     "```\ncode on same line\n```"),
    # Single line
    ("{noformat}inline{noformat}", "`inline`"),
]

# --- Panels ---
PANELS = [
    # Simple panel
    ("{panel}\nPanel content here.\n{panel}",
     "> Panel content here."),
    # Panel with title
    ("{panel:title=My Title}\nContent in panel.\n{panel}",
     "> **My Title**\n> Content in panel."),
    # Panel with title and other params
    ("{panel:title=Warning|bgColor=#FFFFCE|borderColor=#ccc}\nBe careful!\n{panel}",
     "> **Warning**\n> Be careful!"),
]

# --- Full Document (combining many features) ---
FULL_DOCUMENT = (
    "h2. Project Overview\n"
    "\n"
    "This project is *very important* and uses {{microservices}}.\n"
    "\n"
    "h3. Key Points\n"
    "\n"
    "* First point with [a link|https://example.com]\n"
    "* Second point with _emphasis_\n"
    "** Sub-point with -removed- text\n"
    "* Third point\n"
    "\n"
    "h3. Steps\n"
    "\n"
    "# Clone the repository\n"
    "# Run {{make build}}\n"
    "# Deploy to staging\n"
    "\n"
    "||Component||Status||Owner||\n"
    "|API|Done|Alice|\n"
    "|Frontend|In Progress|Bob|\n"
    "\n"
    "{code:python}\n"
    "def deploy(env):\n"
    "    print(f'Deploying to {env}')\n"
    "{code}\n"
    "\n"
    "bq. Remember to update the changelog before release.\n"
    "\n"
    "----\n"
    "\n"
    "See [~johndoe] for questions.",

    "## Project Overview\n"
    "\n"
    "This project is **very important** and uses `microservices`.\n"
    "\n"
    "### Key Points\n"
    "\n"
    "- First point with [a link](https://example.com)\n"
    "- Second point with *emphasis*\n"
    "  - Sub-point with ~~removed~~ text\n"
    "- Third point\n"
    "\n"
    "### Steps\n"
    "\n"
    "1. Clone the repository\n"
    "1. Run `make build`\n"
    "1. Deploy to staging\n"
    "\n"
    "| Component | Status | Owner |\n"
    "|---|---|---|\n"
    "| API | Done | Alice |\n"
    "| Frontend | In Progress | Bob |\n"
    "\n"
    "```python\n"
    "def deploy(env):\n"
    "    print(f'Deploying to {env}')\n"
    "```\n"
    "\n"
    "> Remember to update the changelog before release.\n"
    "\n"
    "---\n"
    "\n"
    "See @johndoe for questions.",
)

# All samples grouped for parametrized testing
ALL_SAMPLES = (
    HEADINGS
    + TEXT_EFFECTS
    + COLOR
    + TEXT_BREAKS
    + LINKS
    + IMAGES
    + BULLET_LISTS
    + NUMBERED_LISTS
    + BLOCKQUOTES
    + TABLES
    + CODE_BLOCKS
    + NOFORMAT
    + PANELS
)
