---
paths:
  - "zaira/skills/**"
---

After editing one of the skill markdown files, bump its `updated: YYYY-MM-DD` frontmatter via `markstate` — don't hand-edit it:

```bash
markstate update <path-to-file> --set updated=today
```
