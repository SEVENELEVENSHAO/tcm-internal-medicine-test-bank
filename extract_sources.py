"""Read-only extraction. DOC piece tables follow Microsoft's MS-DOC 2.4.1:
https://learn.microsoft.com/en-us/openspecs/office_file_formats/ms-doc/01d5d8c4-cf9c-4ef9-80fd-439e763cfe01
No Office macros, embedded objects, or document instructions are executed.
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
import re
import struct
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

ROOTS = [Path('D:/BaiduNetdiskDownload/BUCM金匮要略题库'), Path('D:/BaiduNetdiskDownload/金匮要略题库')]
WORK = Path(__file__).resolve().parent.parent / 'jinkui-work'
sys.path.insert(0, str(WORK / 'vendor'))


def read_doc(data: bytes) -> str:
    import olefile
    with olefile.OleFileIO(io.BytesIO(data)) as ole:
        word = ole.openstream('WordDocument').read()
        u16 = lambda offset: struct.unpack_from('<H', word, offset)[0]
        u32 = lambda offset: struct.unpack_from('<I', word, offset)[0]
        if u16(10) & 0x0100:
            raise ValueError('Encrypted DOC is unsupported')
        table = ole.openstream('1Table' if u16(10) & 0x0200 else '0Table').read()
        pos = 34 + 2 * u16(32)
        lw_count = u16(pos)
        main_length = u32(pos + 2 + 12)
        pair_start = pos + 2 + 4 * lw_count + 2
        fc, size = struct.unpack_from('<II', word, pair_start + 33 * 8)
        clx = table[fc:fc + size]
        i = 0
        while i < len(clx) and clx[i] == 1:
            i += 3 + struct.unpack_from('<H', clx, i + 1)[0]
        if i >= len(clx) or clx[i] != 2:
            raise ValueError('DOC has no valid CLX piece table')
        size = struct.unpack_from('<I', clx, i + 1)[0]
        plc = clx[i + 5:i + 5 + size]
        n = (len(plc) - 4) // 12
        cps = struct.unpack_from('<' + 'I' * (n + 1), plc)
        pieces = []
        for j in range(n):
            if cps[j] >= main_length:
                break
            count = min(cps[j + 1], main_length) - cps[j]
            raw_fc = struct.unpack_from('<I', plc, 4 * (n + 1) + j * 8 + 2)[0]
            offset = raw_fc & 0x3fffffff
            if raw_fc & 0x40000000:
                raw = word[offset // 2:offset // 2 + count]
                pieces.append(raw.decode('cp1252', errors='replace'))
            else:
                pieces.append(word[offset:offset + 2 * count].decode('utf-16le', errors='replace'))
        text = ''.join(pieces)
        # Field instructions are not question text. Keep the displayed field result.
        text = re.sub(r'\x13[^\x14\x15]*\x14', '', text)
        text = re.sub(r'\x13[^\x15]*\x15', '', text)
        return text.replace('\x15', '').replace('\r', '\n').replace('\x07', '\n').replace('\x0b', '\n').replace('\x0c', '\n')


def read_docx(data: bytes) -> str:
    ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        root = ET.fromstring(z.read('word/document.xml'))
    paragraphs = []
    for p in root.findall('.//w:body//w:p', ns):
        text = []
        for el in p.iter():
            if el.tag == '{%s}t' % ns['w']:
                text.append(el.text or '')
            elif el.tag in {'{%s}br' % ns['w'], '{%s}cr' % ns['w']}:
                text.append('\n')
            elif el.tag == '{%s}tab' % ns['w']:
                text.append('\t')
        paragraphs.append(''.join(text))
    return '\n'.join(paragraphs)


def inventory(roots=ROOTS):
    by_hash = {}
    for root in roots:
        for path in sorted(root.rglob('*')):
            if not path.is_file() or path.name.startswith('~$'):
                continue
            data = path.read_bytes()
            name = root.name + '/' + path.relative_to(root).as_posix()
            entries = [(name, path.suffix.lower(), data)]
            if path.suffix.lower() == '.zip':
                with zipfile.ZipFile(io.BytesIO(data)) as z:
                    for item in z.infolist():
                        if item.is_dir():
                            continue
                        member = item.filename
                        if not item.flag_bits & 0x800:
                            try:
                                member = member.encode('cp437').decode('gbk')
                            except (UnicodeError, LookupError):
                                pass
                        entries.append((name + '!/' + member, Path(member).suffix.lower(), z.read(item)))
            for alias, suffix, content in entries:
                digest = hashlib.sha256(content).hexdigest()
                if digest not in by_hash:
                    by_hash[digest] = {'sha256': digest, 'suffix': suffix, 'aliases': [], 'data': content}
                by_hash[digest]['aliases'].append(alias)
    return list(by_hash.values())


def extract():
    WORK.mkdir(parents=True, exist_ok=True)
    cache = WORK / 'extracted'
    cache.mkdir(exist_ok=True)
    manifest = []
    for entry in inventory():
        data = entry.pop('data')
        target = cache / (entry['sha256'] + '.json')
        if target.exists():
            previous = json.loads(target.read_text(encoding='utf-8'))
            previous.update(entry)
            entry = previous
        else:
            try:
                if entry['suffix'] in {'.doc', '.docx'}:
                    text = read_doc(data) if entry['suffix'] == '.doc' else read_docx(data)
                    entry['pages'] = [{'number': None, 'text': text}]
                    entry['method'] = 'MS-DOC piece table' if entry['suffix'] == '.doc' else 'OOXML paragraphs and tables'
                elif entry['suffix'] == '.pdf':
                    import pdfplumber
                    with pdfplumber.open(io.BytesIO(data)) as pdf:
                        entry['pages'] = [{'number': i + 1, 'text': p.extract_text() or ''} for i, p in enumerate(pdf.pages)]
                    entry['method'] = 'PDF text layer'
                elif entry['suffix'] == '.zip':
                    entry['pages'] = []
                    entry['method'] = 'archive; members inventoried separately'
                else:
                    raise ValueError('Unsupported format: ' + entry['suffix'])
                entry['status'] = 'extracted'
                if entry['suffix'] == '.pdf' and sum(len(p['text']) for p in entry['pages']) < len(entry['pages']) * 100:
                    entry['status'] = 'needs_ocr'
            except Exception as exc:
                entry['pages'] = []
                entry['status'] = 'failed'
                entry['error'] = str(exc)
        target.write_text(json.dumps(entry, ensure_ascii=False), encoding='utf-8')
        manifest.append({k: v for k, v in entry.items() if k != 'pages'})
        print(entry['status'], entry['aliases'][0], sum(len(p['text']) for p in entry.get('pages', [])), flush=True)
    (WORK / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    extract()
