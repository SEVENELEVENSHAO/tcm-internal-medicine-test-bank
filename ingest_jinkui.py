"""Incrementally import the supplied Jin Gui question banks without rebuilding old IDs."""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re
import statistics
import sqlite3
import unicodedata

BASE = Path(__file__).resolve().parent
WORK = BASE.parent / 'jinkui-work'
SUBJECT = '金匮要略'
CHAPTERS = ['绪论', '脏腑经络先后病脉证第一', '痉湿暍病脉证治第二', '百合狐惑阴阳毒病证治第三',
 '疟病脉证并治第四', '中风历节病脉证并治第五', '血痹虚劳病脉证并治第六', '肺痿肺痈咳嗽上气病脉证治第七',
 '奔豚气病脉证治第八', '胸痹心痛短气病脉证治第九', '腹满寒疝宿食病脉证治第十', '五脏风寒积聚病脉证并治第十一',
 '痰饮咳嗽病脉证并治第十二', '消渴小便不利淋病脉证并治第十三', '水气病脉证并治第十四', '黄疸病脉证并治第十五',
 '惊悸吐衄下血胸满瘀血病脉证治第十六', '呕吐哕下利病脉证治第十七', '疮痈肠痈浸淫病脉证并治第十八',
 '趺蹶手指臂肿转筋阴狐疝蛔虫病脉证治第十九', '妇人妊娠病脉证并治第二十', '妇人产后病脉证治第二十一', '妇人杂病脉证并治第二十二']
TYPE_NAMES = {'Single':'单选', 'A1':'A1单选', 'A2':'A2单选', 'A3':'A3共用题干', 'A4':'A4共用题干',
 'B1':'配伍选择', 'Multiple':'多选', 'FillBlank':'填空', 'Term':'名词解释', 'Interpretation':'经义阐释',
 'ShortAnswer':'简答', 'Essay':'论述', 'CaseAnalysis':'病案分析', 'TrueFalse':'判断分析', 'Comparison':'类证鉴别'}
CHOICE_TYPES = {'Single','A1','A2','A3','A4','B1','Multiple'}
CN = {'〇':0,'零':0,'一':1,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9}
NUMBER = re.compile(r'^\s*[·•]?(\d{1,4}|[lIl])\s*(?:[.．、・·`,，]|(?=[\u4e00-\u9fff《“]))\s*(\S.*)$')
KEY_PAIR = re.compile(r'(?<![\d.])(\d{1,4})\s*[.．、:：・·]?\s*([A-Za-z](?:\s*[A-Za-z]){0,4})(?![A-Za-z])')


def cn_num(text):
    if text.isdigit(): return int(text)
    if '十' in text:
        a,b = text.split('十',1)
        return CN.get(a,1)*10 + CN.get(b,0)
    return CN.get(text)


def clean(text):
    return unicodedata.normalize('NFKC', text).replace('\u3000',' ').replace('\x08','').strip()


def chapter_for(text):
    text = clean(text)
    if text in {'绪言','绪论'}: return CHAPTERS[0]
    match = re.search(r'第([一二三四五六七八九十]+)(?:篇)?$', text)
    if match and 8 <= len(text) <= 45:
        n = cn_num(match[1])
        if n and n < len(CHAPTERS): return CHAPTERS[n]
    if len(text)<=45 and '第' in text and re.search(r'脉证|病证|病脉',text):
        # Several original Word headings have a dash in place of “一”.
        prefixes=['脏腑经络先后','痉湿','百合狐惑','疟病','中风历节','血痹虚劳','肺痿肺痈','奔豚气病',
                  '胸痹心痛','腹满寒疝','五脏风寒','痰饮咳嗽','消渴小便','水气病','黄疸病','惊悸吐',
                  '呕吐哕','疮痈肠痈','趺蹶手指','妇人妊娠','妇人产后','妇人杂病']
        for i,prefix in enumerate(prefixes,1):
            if text.startswith(prefix):return CHAPTERS[i]
    return None


def file_chapter(name):
    stem = Path(name).stem
    if '绪论' in stem: return CHAPTERS[0]
    if chapter_for(re.sub(r'^\d+', '', stem)): return chapter_for(re.sub(r'^\d+', '', stem))
    match = re.match(r'(?:第)?([一二三四五六七八九十]+)篇', stem)
    if match and (n := cn_num(match[1])) and n < len(CHAPTERS): return CHAPTERS[n]
    return None


def type_for_header(text):
    value = re.sub(r'[\s_{}$]', '', clean(text)).replace('×','X')
    value = re.sub(r'^\([—-]\)', '', value)
    value = re.sub(r'^[（(]?[一二三四五六七八九十]+[)）、.、】]*', '', value)
    value = value.lstrip('【[（(')
    value = re.sub(r'^金匮要略', '', value)
    value = re.sub(r'A([1234])\1+(?=型题)',r'A\1',value)
    for pattern,kind in [
        (r'^(?:A[1Il]?|A)型题','A1'), (r'^A2型题','A2'), (r'^A3型题','A3'), (r'^A4型题','A4'),
        (r'^B[1Il]?型题','B1'), (r'^(?:X型题|多[项选]+择?题?|多选题)','Multiple'),
        (r'^(?:单[项选]+择题?|单选题)','Single'), (r'^填空','FillBlank'), (r'^名词解释','Term'),
        (r'^(?:经义阐释|阐释)','Interpretation'), (r'^(?:简答|问答)','ShortAnswer'), (r'^论述','Essay'),
        (r'^(?:病[案例]分析|病例分析)','CaseAnalysis'), (r'^判断','TrueFalse'), (r'^类证鉴别','Comparison')]:
        if re.match(pattern, value): return kind
    return None


def file_type(name):
    stem = Path(name).stem
    for key,value in [('单选','Single'),('选择习题','Single'),('多选','Multiple'),('填空','FillBlank'),
        ('名词','Term'),('阐释','Interpretation'),('简答','ShortAnswer'),('论述','Essay'),('病案','CaseAnalysis')]:
        if key in stem: return value
    if re.search(r'A\s*2',stem): return 'A2'
    return 'A1'


def split_options(text):
    # A label can lack punctuation in these Word banks, but must begin a line
    # or follow whitespace. Repeated/missing labels are retained and reviewed.
    pattern = re.compile(r'(?m)(?<![A-Za-z°])([A-E])\s*[.．、:：,，。]\s*|(?:^|(?<=\s))([A-E])(?=[\u4e00-\u9fff《])')
    matches = list(pattern.finditer(text))
    first_a=next((i for i,m in enumerate(matches) if (m[1] or m[2])=='A'),None)
    if first_a is not None:matches=matches[first_a:]
    if len(matches) < 2: return text.strip(), []
    options = []
    for i,m in enumerate(matches):
        end = matches[i+1].start() if i+1 < len(matches) else len(text)
        options.append({'letter':m[1] or m[2], 'text':text[m.end():end].strip()})
    return text[:matches[0].start()].strip(), options


def fingerprint(stem, options, kind, context=''):
    norm = lambda s: re.sub(r'\s+', '', clean(s))
    # Do not merge different option order, option labels, types, or shared cases.
    content = ['A1' if kind=='Single' else kind, norm(context), norm(stem), [(o['letter'],norm(o['text'])) for o in options]]
    return hashlib.sha256(json.dumps(content,ensure_ascii=False).encode()).hexdigest()


@dataclass
class Line:
    text: str
    locator: str
    page: int
    score: float = 1.0


@dataclass
class Question:
    number: str
    kind: str
    chapter: str | None
    lines: list[Line]
    shared: str = ''
    shared_options: list = field(default_factory=list)
    stem: str = ''
    options: list = field(default_factory=list)
    answers: list = field(default_factory=list)
    issues: list = field(default_factory=list)
    shared_min_score: float = 1.0


def source_lines(entry):
    result = []
    for page in entry['pages']:
        number = page['number'] or 1
        ocr_lines = page.get('lines')
        if ocr_lines:
            # Group baselines with a tolerance derived from actual text height.
            # Rounding y to fixed buckets can put C before A on a skewed row.
            heights=[max(pt[1] for pt in r['box'])-min(pt[1] for pt in r['box']) for r in ocr_lines]
            tolerance=max(6,statistics.median(heights)*.65)
            rows=[]
            body_lines=[r for r in ocr_lines if min(pt[1] for pt in r['box'])>=185]
            for r in sorted(body_lines,key=lambda r:sum(pt[1] for pt in r['box'])/len(r['box'])):
                y=sum(pt[1] for pt in r['box'])/len(r['box'])
                if rows and abs(y-rows[-1][0])<=tolerance:
                    rows[-1][1].append(r)
                else:rows.append((y,[r]))
            values=[('  '.join(r['text'] for r in sorted(row,key=lambda r:min(pt[0] for pt in r['box']))),
                     min(r.get('score',1) for r in row)) for _,row in rows]
        else:values=[(t,1) for t in page['text'].splitlines()]
        for i,(text,score) in enumerate(values,1):
            text = clean(text)
            # Verified against the rendered original PDF pages (printed pages
            # 141 and 166): the third answer subheading is A3, not OCR A_{}.
            if entry['suffix']=='.pdf' and any('金匮要略讲义学习指导与习题集.pdf' in a for a in entry['aliases']) and number in {147,172} and text=='$A_{}型题':
                text='A3型题'
            if text:
                locator = f'PDF第{number}页·行{i}' if entry['suffix']=='.pdf' else f'段落{i}'
                result.append(Line(text,locator,number,float(score)))
    return result


def parse_source(entry):
    name = min(entry['aliases'], key=lambda x: ('!/' in x,len(x)))
    kind,chapter = file_type(name),file_chapter(name)
    is_pdf = entry['suffix']=='.pdf'
    is_inline_subjective = Path(name).name in {'金匮要略填空题.docx','金匮要略简答、论述、病例分析.docx'}
    is_selftest = '背诵条文方药' in name
    active = not is_pdf
    answer_mode = False
    questions, answer_sections, diagnostics = [], [], []
    current = None
    answer_lines = []
    section_chapter,section_kind = chapter,kind
    seen_chapters = set()
    shared_lines = []
    shared_options = []
    last_metadata = False

    def finish():
        nonlocal current
        if current is not None:
            questions.append(current)
            current = None

    def flush_answers():
        nonlocal answer_lines,section_chapter,section_kind
        if answer_lines: answer_sections.append((section_chapter,section_kind,answer_lines))
        answer_lines = []
        section_chapter,section_kind = chapter,kind

    for line in source_lines(entry):
        text = line.text
        if is_pdf and (line.page <= 6 or text.isdigit() or '金匮要略讲义学习指导与习题集' in re.sub(r'\s','',text)):
            continue
        if is_pdf and text=='模拟试卷及参考答案':
            finish();flush_answers();active=False
            continue
        if is_pdf and re.fullmatch(r'模拟试卷[一二三四五六七八九十]+',re.sub(r'\s','',text)):
            finish();flush_answers();chapter='附录·'+re.sub(r'\s','',text)
            kind='A1';section_chapter=chapter;section_kind=kind
            active=True;answer_mode=False;shared_lines=[];shared_options=[]
            continue
        new_chapter = chapter_for(text)
        if new_chapter:
            if new_chapter==chapter and is_pdf: continue  # running page header
            finish(); flush_answers()
            if not is_pdf and new_chapter in seen_chapters: answer_mode = True
            seen_chapters.add(new_chapter)
            chapter = new_chapter
            section_chapter = chapter
            if is_pdf: active = False; answer_mode = False
            shared_lines,shared_options = [],[]
            continue
        if re.match(r'^(?:附参.{0,6}(?:案|提示)|(?:[一二三四五六七八九十]+[、.])?参考[答笞]案|答案\s*[:：])',re.sub(r'\s','',text)):
            finish(); flush_answers(); answer_mode = True; active = True
            continue
        if is_pdf and re.match(r'^[一二三四五六][、.](?:内容提要|重难点解析)',re.sub(r'\s','',text)):
            finish();flush_answers();active=False;answer_mode=False
            continue
        if is_pdf and re.match(r'^三[、.]习题',re.sub(r'\s','',text)):
            finish();flush_answers();active=True;answer_mode=False
            continue
        new_kind = type_for_header(text) if len(text)<180 else None
        if new_kind:
            finish();flush_answers();kind=new_kind;section_kind=kind
            shared_lines,shared_options = [],[]
            last_metadata = False
            continue
        if not active: continue
        if answer_mode:
            answer_lines.append(line)
            continue
        if is_selftest:
            if current and text.startswith('当以'):
                current.lines.append(line)
            else:
                finish()
                current=Question(f'段落{len(questions)+1}','FillBlank',chapter,[line],issues=['原文无独立题号'])
            continue
        if re.match(r'^[（(]?\d+\s*[~～—\-至]\s*\d+题',text):
            finish();shared_lines=[line];shared_options=[]
            continue
        if kind in {'A3','A4'} and current is not None and re.match(r'^(?:[\u4e00-\u9fff]{1,8}[,、].{0,3}[男女]|患者|[\u4e00-\u9fff]{0,3}某|[男女][,、])',text):
            # The workbook prints cases without “共用题干” or number ranges.
            # A new patient paragraph following a completed option block starts
            # the next common case, rather than becoming part of option E.
            if len(split_options('\n'.join(l.text for l in current.lines))[1])>=2:
                finish();shared_lines=[line];shared_options=[]
                continue
        # Explicit per-question answer and metadata in the clinical A1/A2 banks.
        match = re.match(r'^【(?:参考答案|答案)】\s*(.*)$',text)
        if match and current:
            current.answers.append({'text':match[1], 'locator':line.locator,'page':line.page,'score':line.score})
            last_metadata=True
            continue
        if re.match(r'^【(?:分数|试题难度|认知层次|知识点|命题人)】',text):
            last_metadata=True
            continue
        # Glossary questions are often packed into a single paragraph.
        if kind=='Term':
            pieces = list(re.finditer(r'(?<!\d)(\d{1,3}|[lIl])\s*[.、・·]\s*(?!\d)',text))
            if pieces:
                for i,m in enumerate(pieces):
                    finish()
                    value=text[m.end():pieces[i+1].start() if i+1<len(pieces) else len(text)]
                    current=Question('1' if m[1] in 'lIl' else m[1],kind,chapter,[Line(value,line.locator,line.page,line.score)])
                continue
        match = NUMBER.match(text)
        if is_inline_subjective and match and not re.match(r'^\d{1,4}\s*[.、,]',text):
            match=None  # Circled-list numerals are answer subpoints in this DOCX.
        if match:
            finish()
            if kind=='B1' and shared_lines:
                _,shared_options=split_options('\n'.join(l.text for l in shared_lines))
            number='1' if match[1] in 'lIl' else match[1]
            current=Question(number,kind,chapter,[Line(match[2],line.locator,line.page,line.score)],
                             '\n'.join(l.text for l in shared_lines),list(shared_options),
                             shared_min_score=min((l.score for l in shared_lines),default=1))
            last_metadata=False
        elif re.fullmatch(r'[A-Za-z]{1,5}',text) and current and current.kind in CHOICE_TYPES:
            current.answers.append({'text':text.upper(),'locator':line.locator,'page':line.page,'score':line.score})
        elif re.match(r'^A\s*[.、:：]',text) and kind=='B1':
            # A new option pool begins after a completed B1 question group.
            finish();shared_options=[];shared_lines=[line]
        elif current is None and (kind in {'B1','A3','A4'} or shared_lines):
            shared_lines.append(line)
            _,opts=split_options('\n'.join(l.text for l in shared_lines))
            if opts: shared_options=opts
        elif current is not None and not last_metadata:
            current.lines.append(line)
    finish();flush_answers()

    # Finalize question stems and pull inline answers away from the visible text.
    for q in questions:
        lines=list(q.lines)
        if is_inline_subjective and q.kind not in CHOICE_TYPES:
            boundary=1
            if q.kind=='CaseAnalysis':
                boundary=next((i for i,l in enumerate(lines) if re.match(r'^(?:诊断|证型)\s*[:：]',l.text)),len(lines))
            answer='\n'.join(l.text for l in lines[boundary:]).strip()
            if answer:
                q.answers.append({'text':answer,'locator':lines[boundary].locator,'page':lines[boundary].page,'score':1})
                lines=lines[:boundary]
        text='\n'.join(l.text for l in lines)
        if q.kind in CHOICE_TYPES:
            # Only letter-only parenthetical keys are removed, never prose.
            for m in list(re.finditer(r'[（(]\s*([A-Za-z]{1,5})\s*[)）]',text)):
                q.answers.append({'text':m[1].upper(),'locator':q.lines[0].locator,'page':q.lines[0].page,'score':q.lines[0].score})
            text=re.sub(r'[（(]\s*[A-Za-z]{1,5}\s*[)）]','（　）',text)
            q.stem,q.options=split_options(text)
            if not q.options and q.shared_options: q.options=q.shared_options
            if q.shared and q.shared_options:
                q.shared=split_options(q.shared)[0]
            labels=[o['letter'] for o in q.options]
            if len(q.options)<2 or labels!=list('ABCDE'[:len(labels)]) or any(not o['text'] for o in q.options):
                q.issues.append('选项缺失、重复或编号不连续')
            if any(l.score<0.80 for l in q.lines): q.issues.append('OCR含低置信度行')
            if q.shared_min_score<.80:q.issues.append('共用题干或选项OCR含低置信度行')
        else:
            q.stem=text.strip()
        if not q.stem: q.issues.append('题干为空')

    # Match chapter-end keys using the entire source/chapter/type/number key.
    by_key=defaultdict(list)
    for q in questions: by_key[(q.chapter,q.kind,q.number)].append(q)
    for matches in by_key.values():
        if len(matches)>1:
            for q in matches:q.issues.append('同篇章同题型题号重复')
    for chapter,kind,lines in answer_sections:
        if kind in CHOICE_TYPES:
            pairs=[]
            numbers=[];letters=[]
            for line in lines:
                found=list(KEY_PAIR.finditer(line.text))
                if found:
                    pairs.extend((m[1], re.sub(r'\s','',m[2]).upper(),line) for m in found)
                elif re.fullmatch(r'\d{1,4}',line.text): numbers.append((line.text,line))
                elif re.fullmatch(r'[A-Za-z]{1,5}',line.text): letters.append((line.text.upper(),line))
            if numbers or letters:
                if len(numbers)==len(letters):
                    pairs.extend((n[0],a[0],a[1]) for n,a in zip(numbers,letters))
                else: diagnostics.append({'chapter':chapter,'type':kind,'issue':'答案表题号/答案数不一致','numbers':len(numbers),'answers':len(letters)})
            for number,answer,line in pairs:
                matches=by_key.get((chapter,kind,number),[])
                if len(matches)==1:
                    matches[0].answers.append({'text':answer,'locator':line.locator,'page':line.page,'score':line.score})
                else:
                    diagnostics.append({'chapter':chapter,'type':kind,'number':number,'issue':'答案题号未唯一匹配','matches':len(matches)})
                    for q in matches:q.issues.append('同篇章同题型题号重复')
        else:
            blocks=[];current_answer=None
            for line in lines:
                match=NUMBER.match(line.text)
                if match:
                    if current_answer:blocks.append(current_answer)
                    current_answer=(('1' if match[1] in 'lIl' else match[1]),[Line(match[2],line.locator,line.page,line.score)])
                elif current_answer:current_answer[1].append(line)
            if current_answer:blocks.append(current_answer)
            for number,answer_lines in blocks:
                matches=by_key.get((chapter,kind,number),[])
                if len(matches)==1:
                    answer='\n'.join(l.text for l in answer_lines).strip()
                    q=matches[0]
                    # Some chapter files repeat the question before its answer.
                    if answer.startswith(q.stem):answer=answer[len(q.stem):].strip()
                    if answer and not re.fullmatch(r'[（(]?无答案[)）]?',answer):
                        q.answers.append({'text':answer,'locator':answer_lines[0].locator,'page':answer_lines[0].page,
                                          'score':min(l.score for l in answer_lines)})
                else:
                    diagnostics.append({'chapter':chapter,'type':kind,'number':number,'issue':'主观题答案题号未唯一匹配','matches':len(matches)})
    return questions,diagnostics


def resolve_answer(q):
    candidates=[]
    for a in q.answers:
        value=a['text'].strip()
        if q.kind in CHOICE_TYPES:
            value=re.sub(r'\s','',value).upper()
            if not re.fullmatch(r'[A-E]{1,5}',value):
                q.issues.append('选择题答案不是有效选项字母');continue
            value=''.join(sorted(set(value)))
            labels={o['letter'] for o in q.options}
            if not set(value)<=labels or (q.kind!='Multiple' and len(value)!=1):
                q.issues.append('答案与题型或选项不一致')
        if a.get('score',1)<.80:q.issues.append('答案OCR含低置信度行')
        candidates.append(value)
    distinct=list(dict.fromkeys(candidates))
    if len(distinct)>1:q.issues.append('原文答案冲突')
    answer='\n\n---\n\n'.join(distinct) or None
    q.issues=list(dict.fromkeys(q.issues))
    status='needs_review' if q.issues else 'source_answer_present' if answer else 'not_in_source'
    return answer,status


def migrate(db):
    columns={r[1] for r in db.execute('PRAGMA table_info(questions)')}
    for name,decl in [('subject',"TEXT NOT NULL DEFAULT '中医内科'"),('chapter','TEXT'),('options_json','TEXT'),
                      ('group_context','TEXT'),('source_locator','TEXT'),('dedupe_key','TEXT')]:
        if name not in columns:db.execute(f'ALTER TABLE questions ADD COLUMN {name} {decl}')
    db.executescript('''
        CREATE UNIQUE INDEX IF NOT EXISTS questions_dedupe_key ON questions(dedupe_key) WHERE dedupe_key IS NOT NULL;
        CREATE INDEX IF NOT EXISTS questions_subject_chapter ON questions(subject,chapter);
        CREATE TABLE IF NOT EXISTS source_aliases(source_id INTEGER REFERENCES sources(id),path TEXT UNIQUE NOT NULL);
        CREATE TABLE IF NOT EXISTS question_occurrences(
            id INTEGER PRIMARY KEY,question_id INTEGER NOT NULL REFERENCES questions(id),
            source_id INTEGER NOT NULL REFERENCES sources(id),page_id INTEGER NOT NULL REFERENCES source_pages(id),
            locator TEXT NOT NULL,item_number TEXT NOT NULL,chapter TEXT,question_type TEXT NOT NULL,
            answer_text TEXT,answer_status TEXT NOT NULL,issues_json TEXT NOT NULL,
            UNIQUE(source_id,locator,question_type,item_number));
        CREATE TABLE IF NOT EXISTS import_sources(
            source_id INTEGER PRIMARY KEY REFERENCES sources(id),sha256 TEXT NOT NULL,parser_version TEXT NOT NULL);
    ''')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--database',type=Path,default=BASE.parent/'test_bank.sqlite')
    args=parser.parse_args()
    db=sqlite3.connect(args.database)
    db.execute('PRAGMA foreign_keys=ON')
    migrate(db)
    reports=[]
    entries=[json.loads(p.read_text(encoding='utf-8')) for p in sorted((WORK/'extracted').glob('*.json'))]
    # Stable ordering on every run; known chapter files also enrich aggregate-bank records.
    entries.sort(key=lambda e:min(e['aliases']))
    for entry in entries:
        if entry['suffix']=='.zip':
            reports.append({'source':min(entry['aliases']),'aliases':entry['aliases'],'status':'archive_inventoried','questions':0});continue
        name=min(entry['aliases'],key=lambda x:('!/' in x,len(x)))
        is_reference=any(s in name for s in ['【知识点】','【教参】','【书】'])
        ocr_dir=WORK/'ocr'/entry['sha256']
        ocr_count=len(list(ocr_dir.glob('*.json'))) if ocr_dir.exists() else 0
        if entry['status']=='needs_ocr' and not is_reference:
            if ocr_count!=len(entry['pages']):raise RuntimeError(f'OCR incomplete: {name}: {ocr_count}/{len(entry["pages"])}')
            entry['pages']=[json.loads(p.read_text(encoding='utf-8')) for p in sorted(ocr_dir.glob('*.json'))]
            entry['method']='local PP-OCRv5; original page numbers retained'
            entry['status']='extracted_ocr'
        existing=db.execute('SELECT id FROM sources WHERE sha256=?',(entry['sha256'],)).fetchone()
        if existing:source_id=existing[0]
        else:
            source_id=db.execute('INSERT INTO sources(filename,type,role,sha256,extraction_note) VALUES(?,?,?,?,?)',
                (name,entry['suffix'][1:],'reference' if is_reference else 'test_bank',entry['sha256'],entry.get('method',entry['status']))).lastrowid
        for alias in entry['aliases']:db.execute('INSERT OR IGNORE INTO source_aliases VALUES(?,?)',(source_id,alias))
        page_ids={}
        for p in entry['pages']:
            n=p['number'] or 1
            old=db.execute('SELECT id FROM source_pages WHERE source_id=? AND page_number=?',(source_id,n)).fetchone()
            if old:page_ids[n]=old[0]
            else:
                page_ids[n]=db.execute('INSERT INTO source_pages(source_id,page_number,text) VALUES(?,?,?)',(source_id,n,p['text'])).lastrowid
                db.execute('INSERT INTO page_search VALUES(?,?,?)',(name,n,p['text']))
        if is_reference:
            reports.append({'source':name,'aliases':entry['aliases'],'status':'reference_scanned' if entry['status']=='needs_ocr' else 'reference','questions':0})
            continue
        if not entry['pages']:raise RuntimeError(f'Failed extraction: {name}')
        questions,diagnostics=parse_source(entry)
        counts=Counter();new_count=0;review=[]
        for q in questions:
            answer,status=resolve_answer(q)
            counts[status]+=1
            digest=fingerprint(q.stem,q.options,q.kind,q.shared)
            existing=db.execute('SELECT id FROM questions WHERE dedupe_key=?',(digest,)).fetchone()
            page_id=page_ids[q.lines[0].page]
            locator=q.lines[0].locator
            if q.lines[-1].locator!=locator:locator+='至'+q.lines[-1].locator
            if existing:
                qid=existing[0]
                if q.chapter:db.execute('UPDATE questions SET chapter=COALESCE(chapter,?) WHERE id=?',(q.chapter,qid))
            else:
                qid=db.execute('''INSERT INTO questions(source_id,page_id,item_number,question_text,answer_text,answer_status,
                    topic,question_type,extraction_status,subject,chapter,options_json,group_context,source_locator,dedupe_key)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (source_id,page_id,q.number,q.stem,answer,status,None,q.kind,'; '.join(q.issues) or 'source_parsed',
                     SUBJECT,q.chapter,json.dumps(q.options,ensure_ascii=False),q.shared,locator,digest)).lastrowid
                new_count+=1
            db.execute('''INSERT INTO question_occurrences(question_id,source_id,page_id,locator,item_number,chapter,question_type,
                answer_text,answer_status,issues_json) VALUES(?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(source_id,locator,question_type,item_number) DO UPDATE SET
                answer_text=excluded.answer_text,answer_status=excluded.answer_status,issues_json=excluded.issues_json''',
                (qid,source_id,page_id,locator,q.number,q.chapter,q.kind,answer,status,json.dumps(q.issues,ensure_ascii=False)))
            # Each occurrence owns its evidence. Avoid duplicate evidence on reimport.
            evidence_type='jinkui:'+str(source_id)+':'+locator+':'+q.kind+':'+q.number
            db.execute('DELETE FROM answer_evidence WHERE question_id=? AND evidence_type=?',(qid,evidence_type))
            for a in q.answers:
                db.execute('INSERT INTO answer_evidence(question_id,evidence_type,evidence_text,source_page_id,confidence) VALUES(?,?,?,?,?)',
                    (qid,evidence_type,a['locator']+'：'+a['text'],page_ids[a['page']],'source_text' if a.get('score',1)>=.80 else 'needs_review'))
            if q.issues:review.append({'number':q.number,'chapter':q.chapter,'type':q.kind,'locator':locator,'issues':list(dict.fromkeys(q.issues))})
        db.execute('INSERT OR REPLACE INTO import_sources VALUES(?,?,?)',(source_id,entry['sha256'],'jinkui-v1'))
        reports.append({'source':name,'aliases':entry['aliases'],'status':entry['status'],'questions':len(questions),
                        'new_at_first_encounter':new_count,'answer_status':dict(counts),'review':review,'diagnostics':diagnostics})
        print(name,len(questions),dict(counts),flush=True)
    # Resolve merged occurrences conservatively; any conflicting key stays ungraded.
    for (qid,) in db.execute('SELECT id FROM questions WHERE subject=?',(SUBJECT,)).fetchall():
        occurrences=db.execute('SELECT answer_text,answer_status,issues_json FROM question_occurrences WHERE question_id=?',(qid,)).fetchall()
        answers=list(dict.fromkeys(a for a,_,_ in occurrences if a))
        issues=list(dict.fromkeys(issue for _,_,raw in occurrences for issue in json.loads(raw)))
        if len(answers)>1:issues.append('多个来源答案不一致，需人工核对')
        status='needs_review' if issues else 'source_answer_present' if answers else 'not_in_source'
        db.execute('UPDATE questions SET answer_text=?,answer_status=?,extraction_status=? WHERE id=?',
                   ('\n\n---\n\n'.join(answers) or None,status,'; '.join(issues) or 'source_parsed',qid))
    db.commit()
    assert not db.execute('PRAGMA foreign_key_check').fetchall()
    summary={'subject':SUBJECT,'unique_files':len(entries),'file_occurrences':sum(len(e['aliases']) for e in entries),
             'question_occurrences':db.execute('SELECT COUNT(*) FROM question_occurrences').fetchone()[0],
             'unique_questions':db.execute('SELECT COUNT(*) FROM questions WHERE subject=?',(SUBJECT,)).fetchone()[0],
             'answer_status':dict(db.execute('SELECT answer_status,COUNT(*) FROM questions WHERE subject=? GROUP BY answer_status',(SUBJECT,))),
             'types':dict(db.execute('SELECT question_type,COUNT(*) FROM questions WHERE subject=? GROUP BY question_type',(SUBJECT,))),
             'sources':reports}
    (WORK/'import-report.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    db.close()
    print('SUMMARY',json.dumps({k:v for k,v in summary.items() if k!='sources'},ensure_ascii=False))


if __name__=='__main__':main()
