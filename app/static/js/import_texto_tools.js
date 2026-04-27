/* Ferramentas para "editar texto bruto" na revisão de importação (independentes
   da numeração de seções/subseções do relatório). */
(function () {
  'use strict';

  function toRoman(n) {
    if (n < 1) return 'i';
    const v = [1000, 900, 500, 400, 100, 90, 50, 40, 10, 9, 5, 4, 1];
    const s = ['m', 'cm', 'd', 'cd', 'c', 'xc', 'l', 'xl', 'x', 'ix', 'v', 'iv', 'i'];
    let t = n;
    let out = '';
    for (let j = 0; j < v.length; j += 1) {
      while (t >= v[j]) {
        t -= v[j];
        out += s[j];
      }
    }
    return out;
  }

  function stripListMarker(s) {
    const m = /^( *)/.exec(s);
    const sp = m ? m[1] : '';
    let rest = s.slice(sp.length);
    if (/^[-*•]\s+/.test(rest)) rest = rest.replace(/^[-*•]\s+/, '');
    else if (/^\d+[.)]\s+/.test(rest)) rest = rest.replace(/^\d+[.)]\s+/, '');
    else if (/^\(\d+\)\s+/.test(rest)) rest = rest.replace(/^\(\d+\)\s+/, '');
    else if (/^[a-zA-Z][.)]\s+/.test(rest)) rest = rest.replace(/^[a-zA-Z][.)]\s+/, '');
    else if (/^(?:[ivxlcdm]+)[.)]\s*/i.test(rest)) {
      rest = rest.replace(/^(?:[ivxlcdm]+)[.)]\s*/i, '');
    }
    return sp + rest;
  }

  function withLines(ta, fn) {
    const val = ta.value;
    const start = ta.selectionStart;
    const end = ta.selectionEnd;
    if (start === end) {
      const lineStart = val.lastIndexOf('\n', start - 1) + 1;
      const lineEndN = val.indexOf('\n', start);
      const lineEnd = lineEndN === -1 ? val.length : lineEndN;
      const line = val.slice(lineStart, lineEnd);
      const next = fn(line, 0);
      ta.value = val.slice(0, lineStart) + next + val.slice(lineEnd);
      const pos = lineStart + next.length;
      ta.setSelectionRange(pos, pos);
      return;
    }
    const block = val.slice(start, end);
    const lines = block.split('\n');
    const out = lines.map((ln, j) => fn(ln, j));
    const nextBlock = out.join('\n');
    ta.value = val.slice(0, start) + nextBlock + val.slice(end);
    ta.setSelectionRange(start, start + nextBlock.length);
  }

  function applyPrefixEachLine(ta, prefixer) {
    withLines(ta, function (line) {
      const m = /^( *)/.exec(line);
      const sp = m ? m[1] : '';
      const withSp = stripListMarker(line);
      const content = withSp.slice(sp.length).replace(/^\s+/, '');
      return sp + prefixer(content);
    });
  }

  function toolBullet(ta) {
    applyPrefixEachLine(ta, function (body) {
      return '- ' + body;
    });
  }

  function toolOl1(ta) {
    let n = 0;
    withLines(ta, function (line) {
      const m = /^( *)/.exec(line);
      const sp = m ? m[1] : '';
      const withSp = stripListMarker(line);
      const content = withSp.slice(sp.length).replace(/^\s+/, '');
      n += 1;
      return sp + n + '. ' + content;
    });
  }

  function toolOla(ta) {
    let n = 0;
    withLines(ta, function (line) {
      const m = /^( *)/.exec(line);
      const sp = m ? m[1] : '';
      const withSp = stripListMarker(line);
      const content = withSp.slice(sp.length).replace(/^\s+/, '');
      n += 1;
      const ch = String.fromCharCode('a'.charCodeAt(0) + ((n - 1) % 26));
      return sp + ch + ') ' + content;
    });
  }

  function toolOli(ta) {
    let n = 0;
    withLines(ta, function (line) {
      const m = /^( *)/.exec(line);
      const sp = m ? m[1] : '';
      const withSp = stripListMarker(line);
      const content = withSp.slice(sp.length).replace(/^\s+/, '');
      n += 1;
      return sp + toRoman(n) + '. ' + content;
    });
  }

  function toolIndent(ta) {
    withLines(ta, function (line) {
      if (!line.trim()) return line;
      return '  ' + line;
    });
  }

  function toolOutdent(ta) {
    withLines(ta, function (line) {
      if (line.length >= 2 && line.slice(0, 2) === '  ') return line.slice(2);
      return line;
    });
  }

  window.sraImportTextoTool = function (ta, action) {
    if (!ta || !action) return;
    const a = String(action);
    if (a === 'bullet') toolBullet(ta);
    else if (a === 'ol1') toolOl1(ta);
    else if (a === 'ola') toolOla(ta);
    else if (a === 'oli') toolOli(ta);
    else if (a === 'indent') toolIndent(ta);
    else if (a === 'outdent') toolOutdent(ta);
  };
})();
