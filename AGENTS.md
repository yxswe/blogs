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
