# Zaira Markdown/Wiki Syntax Guide

Zaira supports a hybrid of **Markdown** and **Confluence/Jira Wiki Markup** in the same file. Choose whichever syntax is more natural for your content.

## Quick Start

Zaira can convert your content to Confluence in three ways:

1. **Pure Markdown** — Familiar syntax for web developers
2. **Wiki Markup** — Traditional Confluence wiki format
3. **Mixed** — Combine both in the same file

## Markdown Syntax

Standard markdown with Confluence extensions.

### Headings
```markdown
# Heading 1
## Heading 2
### Heading 3
```

### Text Formatting
```markdown
**bold text**
*italic text*
~~strikethrough~~
`inline code`
```

### Links
```markdown
[Link text](https://example.com)
```

### Images
```markdown
![alt text](https://example.com/image.png)
![alt text](./images/local.png)  # Local images uploaded as attachments
```

### Lists

**Unordered:**
```markdown
* Item 1
* Item 2
  * Nested item
```

**Ordered:**
```markdown
1. First
2. Second
   1. Nested
```

### Code Blocks
````markdown
```python
def hello():
    print("world")
```

```javascript
console.log("hello");
```
````

### Tables
```markdown
| Header 1 | Header 2 |
|----------|----------|
| Cell 1   | Cell 2   |
| Cell 3   | Cell 4   |
```

### Blockquotes
```markdown
> This is a blockquote
> It can span multiple lines
```

## Confluence Wiki Markup

Traditional Confluence wiki syntax. Useful if you're already familiar with Confluence editing.

### Headings
```
h1. Heading 1
h2. Heading 2
h3. Heading 3
```

### Text Formatting
```
*bold*
_italic_
-strikethrough-
+underline+
??citation??
```

### Links
```
[Link text|https://example.com]
[#anchor-name]
```

### Lists

**Unordered:**
```
* Item 1
* Item 2
** Nested item
```

**Numbered:**
```
# First
# Second
## Nested
```

### Code Blocks
```
{code:language=python}
def hello():
    print("world")
{code}

{code:language=javascript}
console.log("hello");
{code}
```

### Blockquotes
```
bq. This is a blockquote
```

### Tables
```
||Header 1||Header 2||
|Cell 1|Cell 2|
|Cell 3|Cell 4|
```

## Confluence Macros

Use Confluence macros for advanced features. The syntax works in both markdown and wiki markup.

### Basic Syntax
```
{macro-name:param1=value1|param2=value2}
```

### Common Macros

**Info Box:**
```
{info}
This is an info message
{info}

{info:title=Important}
Custom title
{info}
```

**Warning Box:**
```
{warning}
This is a warning
{warning}
```

**Error Box:**
```
{error}
This is an error message
{error}
```

**Page Tree (shows child pages):**
```
{children}
```

**Expanding Section:**
```
{expand:title=Click to expand}
Hidden content here
{expand}
```

**Code Highlighting:**
```
{code:language=python}
code here
{code}
```

## Mixed Markdown and Wiki Syntax

You can use both syntaxes in the same file:

```markdown
# My Document

This is markdown with **bold** text.

h2. Wiki Section

This uses wiki markup like _italic_ text.

{info}
A Confluence macro works in both
{info}

Back to markdown with a [link](https://example.com).

bq. Wiki blockquote here

Final markdown paragraph.
```

When Confluence wiki syntax is detected, the entire document is converted from wiki markup to markdown first, then processed to Confluence storage format.

## Attachment References

Local images are automatically converted to Confluence attachments:

```markdown
![Screenshot](./images/screenshot.png)
```

The image will be:
1. Uploaded to the Confluence page
2. Referenced as `<ac:image><ri:attachment ri:filename="screenshot.png"/></ac:image>`

## Special Characters

Use HTML entities for special characters:
- `&amp;` for `&`
- `&lt;` for `<`
- `&gt;` for `>`
- `&quot;` for `"`

## Raw XML Passthrough

You can include raw Confluence storage format XML directly in markdown files. This is useful for advanced macros or custom structures:

```markdown
Some content here.

<ac:structured-macro ac:name="status">
  <ac:parameter ac:name="colour">green</ac:parameter>
  <ac:parameter ac:name="title">Done</ac:parameter>
</ac:structured-macro>

Back to markdown.
```

**Note:** Raw XML on its own line works best. Inline XML in paragraphs may be wrapped in `<p>` tags.

## Limitations

### Not Supported
- Task lists (checkboxes)
- Strikethrough with markdown `~~text~~` (use wiki `-text-`)
- Underline (use wiki `+text+`)
- Text colors (use `{color:red}text{color}`)
- Column layouts
- Custom panels beyond info/warning/error

### Workaround
For unsupported features, use raw Confluence macros or storage format XML:

```
{status:green|done}
{color:blue}Colored text{color}
{card:title=Card Title}
Card content
{card}

OR raw XML:

<ac:structured-macro ac:name="status">
  <ac:parameter ac:name="colour">green</ac:parameter>
</ac:structured-macro>
```

## Examples

### Example 1: Mixed Format
```markdown
---
confluence: 123456
title: Release Notes
---

# Version 2.0

## Features

* New dashboard
* Performance improvements
* Bug fixes

h3. Installation

{code:language=bash}
npm install --save mypackage@2.0
{code}

{info:title=Breaking Changes}
Update your config file
{info}

bq. See migration guide for details
```

### Example 2: Wiki Heavy
```
h1. API Documentation

h2. Authentication

_Use token-based auth_

{code:language=python}
headers = {"Authorization": "Bearer TOKEN"}
{code}

h3. Endpoints

||Method||Path||
|GET|/api/users|
|POST|/api/users|

bq. Rate limit: 100 req/min
```

### Example 3: Pure Markdown
```markdown
# User Guide

## Getting Started

Follow these steps:

1. Download the tool
2. Install dependencies
3. Run the setup

```bash
./setup.sh
```

**Important:** Review the config before running.

[See full docs](https://docs.example.com)
```

## Tips

1. **Use markdown for structure** — Headings, lists, basic formatting
2. **Use wiki for Confluence features** — Macros, advanced blocks
3. **Avoid mixing in single paragraph** — Use blocks/sections
4. **Tables work in both** — Choose whichever you prefer
5. **Test round-trip** — Get page, edit, push back

## Front Matter

Use YAML front matter to link to existing Confluence pages:

```yaml
---
confluence: 1234567  # Page ID to update
title: My Page
labels: [documentation, guide]
---

# Page content here
```

Run `zaira wiki put file.md` to sync to Confluence.
