/** Keep the HTML entry's asset URLs aligned with the actual built bytes. */
import { createHash } from 'node:crypto';
import { readFile, writeFile } from 'node:fs/promises';

const entry = new URL('../../static/index.html', import.meta.url);
let source = await readFile(entry, 'utf8');
for (const name of ['style.css', 'app.js']) {
  const bytes = await readFile(new URL(`../../static/${name}`, import.meta.url));
  const stamp = createHash('sha256').update(bytes).digest('hex').slice(0, 12);
  const pattern = new RegExp(`(["'])/static/${name.replace('.', '\\.')}\\?v=[^"']+\\1`, 'g');
  if ((source.match(pattern) || []).length !== 1) throw new Error(`Expected one versioned ${name} entry`);
  source = source.replace(pattern, `"/static/${name}?v=${stamp}"`);
}
await writeFile(entry, source);
process.stdout.write('build:stamp → asset URLs match built content\n');
