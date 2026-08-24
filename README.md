# yxswe's bilingual blog

一个由仓库内 Markdown 文件驱动的中英双语个人博客，使用 [Astro](https://astro.build/) 构建并部署到 GitHub Pages。

## 本地运行

```bash
npm install
npm run dev
```

生产构建：

```bash
npm run build
npm run preview
```

## 添加文章

每篇文章都必须同时提供完整的简体中文和英文版本。构建会执行 `npm run check:bilingual`；缺少任一语言、配对信息不一致或元数据不完整时会直接失败。

在仓库中创建一个目录，并添加 Markdown 文件。例如：

```text
my-new-post/
└── README.md
```

推荐在文件开头添加元数据：

```yaml
---
title: 文章标题
description: 一句话摘要
lang: zh # 或 en
translationKey: article-unique-key # 中英文版本使用相同值
date: 2026-08-24
tags:
  - AI
  - Engineering
featured: false
---
```

同一篇文章的中文和英文文件使用相同的 `translationKey`，语言切换器就会直接跳转到对应译文。例如：

```text
deepseek-harness/
├── README.md  # lang: zh, translationKey: deepseek-harness
└── en.md      # lang: en, translationKey: deepseek-harness
```

访客可以在中文和英文之间切换，网站会在浏览器中记住选择。由于双语版本是强制要求，文章页语言切换会直接打开对应译文。

然后正常书写 Markdown 即可。提交到 `main` 后，GitHub Actions 会自动重新构建和发布网站。

对中文正文进行实质修改时，必须在同一次提交中同步更新英文译文，反之亦然。适用于 Agent 的完整内容规则见 [`AGENTS.md`](./AGENTS.md)。

站点会读取仓库中除 `README.md`、`CONTRIBUTING.md`、`.github/`、`src/` 和 `node_modules/` 以外的全部 Markdown 文件。目录名会成为文章 URL，例如 `DSH/README.md` 对应 `/posts/dsh/`。没有元数据的旧文章也可以使用：标题取第一个一级标题，语言根据正文自动判断。

## 首次启用 GitHub Pages

进入仓库的 **Settings → Pages → Build and deployment**，将 Source 设为 **GitHub Actions**。此后推送到 `main` 即会自动部署到：

<https://yxswe.github.io/blogs/>
