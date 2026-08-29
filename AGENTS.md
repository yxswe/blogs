# Repository rules for agents

## Mandatory bilingual publishing

- Every blog post must have both a Simplified Chinese version and an English version. Never add, publish, rename, move, or substantially edit only one language.
- Keep each translation pair in the same article directory. Use `README.md` for Chinese and `en.md` for English unless an existing pair already follows another convention.
- Both files must include frontmatter with `title`, `description`, `lang`, `translationKey`, `date`, `tags`, and `featured`.
- Set `lang: zh` on the Chinese file and `lang: en` on the English file. Both versions must use the exact same non-empty `translationKey`.
- Keep `date`, `tags`, and `featured` aligned across the pair. Translate the title, description, headings, prose, captions, and other reader-facing text while preserving code, commands, URLs, and technical meaning.
- When one language changes, update its paired translation in the same change. A translation must be complete; placeholders, summaries of the other version, and machine-translation notes do not count.
- Before finishing any content change, run `npm run check:bilingual` and `npm run build`. Do not commit or push if either command fails.

The bilingual validator in `scripts/check-bilingual.mjs` is the executable source of truth for pair completeness and metadata consistency.

## Contextual coherence

- After every content edit, reread the surrounding paragraphs and subsection as a whole. Ensure the revised text connects naturally with what comes before and after, keeps terminology consistent, and introduces no repetition, contradiction, abrupt transition, or dangling reference; revise adjacent text when necessary.

## One article per development branch

- Each development branch must be dedicated to exactly one blog article, including its Chinese and English files.
- Do not add or substantially edit multiple article directories on the same development branch. Move unrelated article work to a separate branch.
- Repository-wide supporting changes required by that article are allowed, but they must remain directly related to the article being developed.

## Pull request language

- Write every pull request title and description entirely in English.
