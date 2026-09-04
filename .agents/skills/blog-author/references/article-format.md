# Article format

Create both files together in one article directory:

- `README.md`: Simplified Chinese
- `en.md`: English

Use this frontmatter shape. In this repository, `date` is the article's last-update date.

```yaml
---
title: "Localized title"
description: "Localized description"
lang: zh # use en in en.md
translationKey: "stable-non-empty-key-shared-by-both-files"
date: YYYY-MM-DD
tags:
  - shared-tag
featured: false
---
```

Requirements:

- Include exactly the required fields `title`, `description`, `lang`, `translationKey`, `date`, `tags`, and `featured`; add other fields only if the repository schema later requires them.
- Translate `title` and `description`.
- Use `lang: zh` in `README.md` and `lang: en` in `en.md`.
- Keep `translationKey`, `date`, tags in the same order, and `featured` identical across the pair.
- Refresh the matching `date` in both files whenever either article version is materially updated.
- Put the first prose paragraph immediately after the frontmatter (or after an existing required title convention). It must plainly state the article's scope and key conclusions.
- Follow that paragraph with the detailed development of the topic. Translate headings, prose, captions, callouts, and other reader-facing text completely.
