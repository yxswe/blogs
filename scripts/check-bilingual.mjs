import { readdir, readFile } from 'node:fs/promises';
import { extname, join, relative, sep } from 'node:path';

const root = process.cwd();
const ignoredDirectories = new Set(['.astro', '.git', '.github', 'dist', 'node_modules', 'public', 'scripts', 'src']);
const ignoredRootFiles = new Set(['README.md', 'CONTRIBUTING.md', 'AGENTS.md']);
const requiredFields = ['title', 'description', 'lang', 'translationKey', 'date', 'tags', 'featured'];

async function collectMarkdown(directory = root) {
  const entries = await readdir(directory, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    if (entry.isDirectory() && ignoredDirectories.has(entry.name)) continue;
    const path = join(directory, entry.name);
    if (entry.isDirectory()) files.push(...await collectMarkdown(path));
    else if (extname(entry.name).toLowerCase() === '.md' && !(directory === root && ignoredRootFiles.has(entry.name))) files.push(path);
  }
  return files;
}

function parseFrontmatter(source, file) {
  const match = source.match(/^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)/);
  if (!match) throw new Error(`${file}: missing YAML frontmatter`);
  const block = match[1];
  const value = field => block.match(new RegExp(`^${field}:\\s*(.+)$`, 'm'))?.[1]?.trim();
  const tagsBlock = block.match(/^tags:\s*\r?\n((?:\s+-\s+.+\r?\n?)*)/m)?.[1] ?? '';
  const data = Object.fromEntries(requiredFields.map(field => [field, field === 'tags' ? [...tagsBlock.matchAll(/^\s+-\s+(.+)$/gm)].map(item => item[1].trim()) : value(field)]));
  const missing = requiredFields.filter(field => field === 'tags' ? data.tags.length === 0 : !data[field]);
  if (missing.length) throw new Error(`${file}: missing required frontmatter field(s): ${missing.join(', ')}`);
  if (data.lang !== 'zh' && data.lang !== 'en') throw new Error(`${file}: lang must be zh or en`);
  return data;
}

const errors = [];
const pairs = new Map();
for (const path of await collectMarkdown()) {
  const file = relative(root, path).split(sep).join('/');
  try {
    const data = parseFrontmatter(await readFile(path, 'utf8'), file);
    const pair = pairs.get(data.translationKey) ?? [];
    pair.push({ file, ...data });
    pairs.set(data.translationKey, pair);
  } catch (error) {
    errors.push(error.message);
  }
}

for (const [key, pair] of pairs) {
  for (const lang of ['zh', 'en']) {
    const matches = pair.filter(post => post.lang === lang);
    if (matches.length !== 1) errors.push(`${key}: expected exactly one ${lang} version, found ${matches.length}`);
  }
  if (new Set(pair.map(post => post.date)).size > 1) errors.push(`${key}: date must match across translations`);
  if (new Set(pair.map(post => post.featured)).size > 1) errors.push(`${key}: featured must match across translations`);
  if (new Set(pair.map(post => JSON.stringify(post.tags))).size > 1) errors.push(`${key}: tags must match across translations`);
}

if (errors.length) {
  console.error(`Bilingual content validation failed:\n- ${errors.join('\n- ')}`);
  process.exit(1);
}

console.log(`Bilingual content validation passed for ${pairs.size} article pair(s).`);
