import { defineCollection } from 'astro:content';
import { glob } from 'astro/loaders';

const posts = defineCollection({
  loader: glob({
    base: '.',
    pattern: [
      '**/*.md',
      '!node_modules/**',
      '!src/**',
      '!.github/**',
      '!README.md',
      '!CONTRIBUTING.md',
      '!AGENTS.md',
    ],
  }),
});

export const collections = { posts };
