---
name: blog-author
description: Develop and write bilingual posts for this repository through a required multi-round discovery process. Use when a user is exploring a possible blog topic, asking open-ended questions that may become a post, refining an article thesis or audience, or asking to draft, revise, or publish a blog article.
---

# Blog Author

Treat blog creation as two distinct stages: discovery and writing. Stay in discovery until the user explicitly authorizes the transition to writing.

## Stage 1: Explore and maintain the draft

1. Start in discovery even when the user asks for a blog immediately. Explain briefly that the topic needs exploration before drafting.
2. Follow the user's curiosity. If they begin with vague questions, answer and investigate those questions instead of forcing a questionnaire or prematurely choosing a thesis.
3. Conduct at least two substantive, user-involved rounds of brainstorming and exploration. Internal planning, merely restating the user's words, or asking a checklist all at once does not count as a round. Continue beyond two rounds while important boundaries or decisions remain unclear. In each round:
   - surface useful distinctions, tradeoffs, examples, counterarguments, or unknowns;
   - research claims when external or repository evidence would improve accuracy;
   - summarize what became clearer and ask only the few next questions that naturally advance the topic;
   - update the draft document after every meaningful exchange.
4. As soon as a possible article topic emerges, choose its intended article directory using the repository's existing organization and create that directory before any publishable prose. Create `<article-directory>/.draft/draft.md` from [references/draft-template.md](references/draft-template.md). The draft must stay with the article it will produce; do not place it in a repository-wide draft directory. If the topic or slug changes materially, move the article directory and its draft together.
5. Record evidence separately from interpretation. Include source links, relevant dates, and uncertainty. Never invent citations, facts, user preferences, or decisions.
6. Gradually make the following explicit in the draft:
   - the central question and why it matters;
   - scope in and scope out;
   - likely readers and their assumed knowledge;
   - intended depth and technical level;
   - candidate thesis and key conclusions;
   - supporting evidence, examples, objections, and unresolved questions;
   - terminology and outline options;
   - decisions made with the user.
7. Periodically give the user a compact synthesis of the current direction. Offer the writing transition only when the direction, boundary, depth, audience, and evidence are sufficiently clear.

Do not create or substantially write the publishable `README.md` or `en.md` during discovery. Notes, fragments, and possible outlines belong only in `<article-directory>/.draft/draft.md`. The `.draft` directory is temporary working memory and must be excluded from publishing and bilingual validation.

## Require an explicit stage gate

Proceed to Stage 2 only after the user clearly says to begin formal writing, such as “开始写”, “进入写作阶段”, or an equally unambiguous approval made after discovery. A request to keep exploring, an answer to a brainstorming question, silence, or vague approval is not authorization.

Before proceeding, update the draft status to `approved-for-writing` and capture the approved direction, audience, depth, conclusions, and outline. If authorization is ambiguous, continue discovery and ask a concise clarifying question.

## Stage 2: Write the bilingual article

Read [references/article-format.md](references/article-format.md) before creating article files. Then:

Unless the user explicitly chooses a specialist audience, assume readers have no prior knowledge of the project, codebase, or internal architecture being discussed. Introduce only concepts needed to understand the article, prefer familiar language over internal terminology, and explain an unavoidable technical term in plain language when it first appears. Do not make readers learn source-code names when describing the same behavior directly would be clearer.

1. Work on a branch dedicated to exactly one article. Preserve unrelated work and move it to another branch or recoverable stash when necessary.
2. In the article directory already established during discovery, create a complete Simplified Chinese `README.md` and English `en.md` alongside the temporary `.draft` directory.
3. Write from the approved draft. Do not silently widen the scope, change the audience, or replace the agreed thesis.
4. Make the first prose paragraph in each language state what the article covers and its key conclusions in plain language. Do not begin with scene-setting, anecdotes, or generic background.
5. Develop the reasoning after that opening. Use evidence, concrete examples, limitations, and transitions appropriate to the approved depth and audience.
6. Translate all reader-facing content completely while preserving code, commands, URLs, and technical meaning. Treat each version as polished native prose rather than a sentence-by-sentence artifact.
7. After every revision to publishable article prose, apply the sibling [blog-review skill](../blog-review/SKILL.md) before validation or handoff. This review is mandatory even for a small rewrite; apply any resulting corrections to both languages.
8. Update the discovery draft's decision log if writing reveals a material scope or thesis decision. Ask the user before making a material departure from what they approved.
9. Keep the draft while either publishable language version is incomplete or validation is failing. Once both versions are complete and both required validation commands pass, automatically delete the article's entire `.draft` directory. Do not leave the discovery draft in the finished article or move it to a repository-wide archive.

## Validate before finishing

Run both commands from the repository root:

```bash
npm run check:bilingual
npm run build
```

Do not commit, push, or claim completion if either fails. Report the failure and keep the article unpublished until it is resolved. Keep pull request titles and descriptions entirely in English.
