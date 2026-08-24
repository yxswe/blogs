import type { Locale } from './lib/posts';

const copy = {
  zh: {
    siteName: 'yxswe / 研习录',
    navWriting: '文章', navAbout: '关于', navSource: '源代码',
    eyebrow: '工程 · AI · 系统思考',
    headlineA: '记录技术的', headlineB: '深层结构。',
    intro: '这里是 yxswe 的个人数字花园。我写 AI Agent、软件工程，以及那些值得被拆开看清的系统。',
    explore: '开始阅读', source: '查看 GitHub', latest: '最新文章', all: '全部',
    search: '搜索文章…', empty: '没有找到匹配的文章。', article: '篇文章',
    allLanguages: '中英双语内容', aboutTitle: '持续理解，持续构建。',
    aboutBody: '我关注复杂系统如何被设计、实现与解释。这个网站的每篇文章都直接来自 GitHub 仓库中的 Markdown 文件。',
    back: '返回文章', toc: '本页目录', updated: '发布于', sourceFile: '在 GitHub 编辑',
    footer: '以代码与文字，记录正在发生的思考。', skip: '跳到正文',
  },
  en: {
    siteName: 'yxswe / FIELD NOTES',
    navWriting: 'Writing', navAbout: 'About', navSource: 'Source',
    eyebrow: 'ENGINEERING · AI · SYSTEMS',
    headlineA: 'Notes on the', headlineB: 'structures beneath.',
    intro: "yxswe's personal digital garden—writing about AI agents, software engineering, and systems worth understanding from the inside out.",
    explore: 'Start reading', source: 'View on GitHub', latest: 'Latest writing', all: 'All',
    search: 'Search articles…', empty: 'No matching articles found.', article: 'articles',
    allLanguages: 'Writing in English & Chinese', aboutTitle: 'Keep learning. Keep building.',
    aboutBody: 'I care about how complex systems are designed, implemented, and explained. Every article on this site is sourced directly from a Markdown file in the GitHub repository.',
    back: 'Back to writing', toc: 'On this page', updated: 'Published', sourceFile: 'Edit on GitHub',
    footer: 'Tracing ideas in code and words.', skip: 'Skip to content',
  },
} as const;

export const t = (locale: Locale) => copy[locale];
