---
name: blog-review
description: Review bilingual blog prose for contextual coherence and logical soundness after any publishable article body is created or edited. Use before validation or handoff whenever reader-facing prose in an article's README.md or en.md changes; do not use for draft-only or metadata-only edits.
---

# Blog Review

Run this review after every change to publishable article prose, including small rewrites. Review both the Chinese and English versions before validation or handoff.

## Review in context

1. Identify every changed paragraph, heading, list, table, caption, and code example in the article pair.
2. Read each changed passage together with its full subsection and the transition into the following subsection. If the change affects the thesis, outline, terminology, or conclusion, reread the complete article.
3. Check contextual coherence:
   - the new text follows naturally from what precedes it;
   - references and pronouns have clear antecedents;
   - terminology remains consistent;
   - no idea is needlessly repeated, contradicted, introduced too late, or left dangling;
   - headings and transitions accurately describe the argument that follows.
4. Check the logic:
   - conclusions follow from the stated evidence or explanation;
   - causal claims do not confuse sequence, correlation, and necessity;
   - conditions, exceptions, and implementation details do not conflict;
   - examples actually demonstrate the claim beside them;
   - the explanation answers the question posed by the section instead of drifting into adjacent topics.
5. Compare the Chinese and English versions for the same meaning, qualifications, examples, and argumentative order. They should read naturally in each language rather than mirror each other mechanically.

## Resolve findings

Fix coherence and logic problems immediately in both language versions when the correction stays within the user's approved scope. After fixing them, reread the affected context and repeat the review until no material issue remains.

Do not silently invent evidence or make a material change to the article's thesis, scope, or conclusions. If resolving a problem requires such a decision, stop and ask the user.

This review is editorial reasoning, not a validator. Run the repository's required bilingual and build checks separately after the review.
