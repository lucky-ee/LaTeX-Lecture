// Reads a JSON array of LaTeX strings on stdin; prints a JSON array of booleans
// (true = KaTeX renders it with throwOnError). Uses the frontend's KaTeX so the
// check matches what the app actually renders.
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const here = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(path.join(here, '../../frontend/package.json'));
const katex = require('katex');

let input = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', (chunk) => { input += chunk; });
process.stdin.on('end', () => {
  const results = JSON.parse(input).map((latex) => {
    try {
      katex.renderToString(latex, { throwOnError: true, trust: false });
      return true;
    } catch {
      return false;
    }
  });
  process.stdout.write(JSON.stringify(results));
});
