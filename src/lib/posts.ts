import type { CollectionEntry } from 'astro:content';

export type Locale = 'zh' | 'en';
export type Post = CollectionEntry<'posts'>;

const stripMarkdown = (value: string) =>
  value
    .replace(/```[\s\S]*?```/g, '')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/!\[[^\]]*\]\([^)]*\)/g, '')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .replace(/[*_>#~|-]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();

export function getTitle(post: Post): string {
  const data = post.data as Record<string, unknown>;
  if (typeof data.title === 'string') return data.title;
  const match = post.body?.match(/^#\s+(.+)$/m);
  return match?.[1]?.trim() ?? post.id.split('/').at(-2) ?? post.id;
}

export function getDescription(post: Post): string {
  const data = post.data as Record<string, unknown>;
  if (typeof data.description === 'string') return data.description;
  const body = post.body?.replace(/^#\s+.+$/m, '') ?? '';
  const quote = body.match(/^>\s+(.+)$/m)?.[1];
  return stripMarkdown(quote || body).slice(0, 150);
}

export function getLanguage(post: Post): Locale {
  const lang = (post.data as Record<string, unknown>).lang;
  if (lang === 'en' || lang === 'zh') return lang;
  return /[\u3400-\u9fff]/.test(`${getTitle(post)} ${post.body?.slice(0, 500)}`) ? 'zh' : 'en';
}

export function getTags(post: Post): string[] {
  const tags = (post.data as Record<string, unknown>).tags;
  if (Array.isArray(tags)) return tags.map(String);
  const category = post.id.split('/')[0];
  return category ? [category] : [];
}

export function getDate(post: Post): Date | undefined {
  const raw = (post.data as Record<string, unknown>).date;
  if (raw instanceof Date && !Number.isNaN(raw.valueOf())) return raw;
  if (typeof raw === 'string' || typeof raw === 'number') {
    const date = new Date(raw);
    if (!Number.isNaN(date.valueOf())) return date;
  }
}

export function getSlug(post: Post): string {
  return post.id.replace(/(^|\/)README(?:\.md)?$/i, '').replace(/\.md$/i, '').replace(/\s+/g, '-').toLowerCase();
}

export function getReadingTime(post: Post, locale: Locale): string {
  const body = post.body ?? '';
  const han = body.match(/[\u3400-\u9fff]/g)?.length ?? 0;
  const words = body.replace(/[\u3400-\u9fff]/g, ' ').match(/[\p{L}\p{N}]+/gu)?.length ?? 0;
  const minutes = Math.max(1, Math.ceil(han / 400 + words / 220));
  return locale === 'zh' ? `${minutes} 分钟阅读` : `${minutes} min read`;
}

export function sortPosts(posts: Post[]): Post[] {
  return [...posts].sort((a, b) => {
    const featured = Number(Boolean((b.data as Record<string, unknown>).featured)) - Number(Boolean((a.data as Record<string, unknown>).featured));
    if (featured) return featured;
    return (getDate(b)?.valueOf() ?? 0) - (getDate(a)?.valueOf() ?? 0) || getTitle(a).localeCompare(getTitle(b));
  });
}
