import { getCollection } from 'astro:content';
import { getDescription, getSlug, getTitle, sortPosts } from '../lib/posts';

const escapeXml = (value: string) => value.replace(/[<>&'\"]/g, char => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;', "'": '&apos;', '"': '&quot;' })[char]!);

export async function GET({ site }: { site: URL }) {
  const posts = sortPosts(await getCollection('posts'));
  const basePath = `${import.meta.env.BASE_URL.replace(/\/$/, '')}/`;
  const base = new URL(basePath, site).href;
  const items = posts.map(post => {
    const url = new URL(`posts/${getSlug(post)}/`, base).href;
    return `<item><title>${escapeXml(getTitle(post))}</title><link>${url}</link><guid>${url}</guid><description>${escapeXml(getDescription(post))}</description></item>`;
  }).join('');
  const xml = `<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>yxswe / Field Notes</title><link>${base}</link><description>Notes on engineering, AI, and systems.</description>${items}</channel></rss>`;
  return new Response(xml, { headers: { 'Content-Type': 'application/rss+xml; charset=utf-8' } });
}
