# yxswe's bilingual blog

A bilingual personal blog driven by Markdown files in this repository, built with [Astro](https://astro.build/) and deployed to GitHub Pages.

## Run locally

```bash
npm install
npm run dev
```

Build and preview the production site:

```bash
npm run build
npm run preview
```

## Add an article

Every article must include complete Simplified Chinese and English versions. The build runs `npm run check:bilingual` and fails if either language is missing, the translation pair is inconsistent, or required metadata is incomplete.

Create a directory in the repository and add both Markdown files. For example:

```text
my-new-post/
├── README.md  # Chinese
└── en.md      # English
```

Add the required frontmatter at the beginning of each file:

```yaml
---
title: Article title
description: A one-sentence summary
lang: zh # or en
translationKey: article-unique-key # use the same value for both languages
date: 2026-08-24
tags:
  - AI
  - Engineering
featured: false
---
```

Use the same `translationKey` for the Chinese and English versions of an article so the language switcher can open the matching translation directly. For example:

```text
deepseek-harness/
├── README.md  # lang: zh, translationKey: deepseek-harness
└── en.md      # lang: en, translationKey: deepseek-harness
```

Visitors can switch between Chinese and English, and the site remembers their choice in the browser. Because both versions are required, the article language switcher always opens the corresponding translation.

Write the article in standard Markdown. After changes reach `main`, GitHub Actions automatically rebuilds and publishes the site.

Whenever one language receives a substantive content change, update its translation in the same commit. See [`AGENTS.md`](./AGENTS.md) for the complete rules followed by coding agents.

The site reads every Markdown file except `README.md`, `CONTRIBUTING.md`, and files under `.github/`, `src/`, and `node_modules/`. Directory names become part of the article URL; for example, `DSH/cordis/README.md` maps to `/posts/dsh/cordis/`. Legacy articles without frontmatter are also supported: the first level-one heading becomes the title, and the language is inferred from the content.

## Enable GitHub Pages for the first time

Open **Settings → Pages → Build and deployment** in the repository and set Source to **GitHub Actions**. Every subsequent push to `main` will deploy automatically to:

<https://yxswe.github.io/blogs/>
