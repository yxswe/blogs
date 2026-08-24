# Yangxiao's bilingual blog

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
date: 2026-08-24
tags:
  - AI
  - Engineering
featured: false
---
```

然后正常书写 Markdown 即可。提交到 `main` 后，GitHub Actions 会自动重新构建和发布网站。

站点会读取仓库中除 `README.md`、`CONTRIBUTING.md`、`.github/`、`src/` 和 `node_modules/` 以外的全部 Markdown 文件。目录名会成为文章 URL，例如 `DSH/README.md` 对应 `/posts/dsh/`。没有元数据的旧文章也可以使用：标题取第一个一级标题，语言根据正文自动判断。

## 首次启用 GitHub Pages

进入仓库的 **Settings → Pages → Build and deployment**，将 Source 设为 **GitHub Actions**。此后推送到 `main` 即会自动部署到：

<https://yxswe.github.io/blogs/>
