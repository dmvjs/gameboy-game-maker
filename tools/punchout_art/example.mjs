// Writes the Joe vs Mac project, exactly as the editor builds it, to stdout. Run by build.py with macOS's
// JavaScriptCore shell (jsc) or Node, since it's a browser module: the result is examples/joe-vs-mac.gbstage.json.
import * as M from '../../editor/model.js';
import { macVsJoe } from '../../editor/mac-vs-joe.js';

const fs = typeof readFile === 'undefined' ? await import('node:fs') : null;   // Node; jsc has readFile/print
const read = path => (fs ? fs.readFileSync(path, 'utf8') : readFile(path));
const out = text => (fs ? process.stdout.write(text + '\n') : print(text));
M.setFont(read('gbstage/font.txt'));
M.setFont(read('gbstage/font-bold.txt'), 'bold');
out(JSON.stringify(M.serialize(macVsJoe())));
