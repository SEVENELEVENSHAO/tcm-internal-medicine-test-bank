"""One data contract shared by the static export and the local read-only API."""
from __future__ import annotations
from collections import Counter
import json
from pathlib import Path
import re
import sqlite3

from ingest_jinkui import CHAPTERS, CHOICE_TYPES, TYPE_NAMES, split_options

SYSTEMS = {
 '肺系':['感冒','咳嗽','哮病','喘证','肺痈','肺痨','肺胀','肺痿','痰饮'],
 '心脑系':['心悸','胸痹心痛','心衰','不寐','头痛','眩晕','中风','痴呆','癫狂','痫病'],
 '脾胃系':['胃痛','痞满','呕吐','噎膈','呃逆','腹痛','泄泻','痢疾','便秘'],
 '肝胆系':['胁痛','黄疸','积聚','鼓胀','瘿病','疟疾','郁证'],
 '肾与膀胱系':['水肿','淋证','癃闭','关格','阳痿','腰痛'],
 '气血津液与杂病':['血证','消渴','汗证','内伤发热','厥证','虚劳','肥胖'],
 '经络肢体系':['痹证','痉证','痿证','颤证']}


def build_payload(path):
    db=sqlite3.connect(f'file:{Path(path).resolve().as_posix()}?mode=ro',uri=True)
    db.row_factory=sqlite3.Row
    questions=[dict(r) for r in db.execute('''SELECT q.*,s.filename source_name,s.type source_type,
        p.page_number source_page FROM questions q JOIN sources s ON s.id=q.source_id
        JOIN source_pages p ON p.id=q.page_id ORDER BY q.id''')]
    occurrences={}
    for r in db.execute('''SELECT o.question_id,o.source_id,s.filename source_name,s.type source_type,
            p.page_number source_page,o.locator,o.item_number,o.chapter FROM question_occurrences o
            JOIN sources s ON s.id=o.source_id JOIN source_pages p ON p.id=o.page_id ORDER BY o.id'''):
        item=dict(r)
        item['source_page']=item['source_page'] if item.pop('source_type')=='pdf' else None
        occurrences.setdefault(item.pop('question_id'),[]).append(item)
    evidence={}
    for r in db.execute('''SELECT e.question_id,e.evidence_text,e.confidence,s.filename source_name,
        s.type source_type,p.page_number source_page FROM answer_evidence e
        LEFT JOIN source_pages p ON p.id=e.source_page_id LEFT JOIN sources s ON s.id=p.source_id ORDER BY e.id'''):
        item=dict(r)
        item['source_page']=item['source_page'] if item.pop('source_type')=='pdf' else None
        evidence.setdefault(item.pop('question_id'),[]).append(item)
    aliases={}
    for r in db.execute('SELECT source_id,path FROM source_aliases ORDER BY path'):
        aliases.setdefault(r['source_id'],[]).append(r['path'])
    sources=[dict(r) for r in db.execute("SELECT id,filename,role,type FROM sources WHERE role='test_bank' ORDER BY id")]
    db.close()
    for q in questions:
        q['subject']=q.get('subject') or '中医内科'
        if q.get('options_json') is not None:
            q['options']=json.loads(q['options_json'])
        else:
            stem,options=split_options(q['question_text'])
            q['question_text']=stem if options else q['question_text']
            q['options']=options
        if q['options'] and not q['question_type']:q['question_type']='Single'
        q['source_page']=q['source_page'] if q['source_type']=='pdf' else None
        q['source_locator']=q.get('source_locator') or (f'PDF第{q["source_page"]}页' if q['source_page'] else f'原文第{q["item_number"]}题')
        q['sources']=occurrences.get(q['id'],[{'source_id':q['source_id'],'source_name':q['source_name'],
            'source_page':q['source_page'],'locator':q['source_locator'],'item_number':q['item_number'],'chapter':q.get('chapter')}])
        q['source_ids']=sorted({s['source_id'] for s in q['sources']})
        q['chapters']=list(dict.fromkeys(c for c in [q.get('chapter'),*[s.get('chapter') for s in q['sources']]] if c))
        q['evidence']=evidence.get(q['id'],[])
        q['evidence_text']='\n'.join(e['evidence_text'] for e in q['evidence']) or None
        q['confidence']=q['evidence'][0]['confidence'] if q['evidence'] else None
        q['answer_page']=', '.join(dict.fromkeys(str(e['source_page']) for e in q['evidence'] if e['source_page'])) or None
        match=re.match(r'^([A-E]{1,5})(?:\s*[.．、:：]|$)',q['answer_text'] or '',re.I)
        key=''.join(sorted(set(match[1].upper()))) if match else None
        labels=[o['letter'] for o in q['options']]
        safe=(q['answer_status']=='source_answer_present' and q['question_type'] in CHOICE_TYPES and
              len(labels)>=2 and labels==list('ABCDE'[:len(labels)]) and key and set(key)<=set(labels) and
              (q['question_type']=='Multiple' or len(key)==1))
        q['answer_key']=key if safe else None
        for field in ['options_json','source_type','dedupe_key','page_id','textbook_page_id']:
            q.pop(field,None)
    for source in sources:
        matching=[q for q in questions if source['id'] in q['source_ids']]
        source.update(question_count=len(matching),subject=matching[0]['subject'] if matching else None,aliases=aliases.get(source['id'],[]))
    topics=Counter(q['topic'] for q in questions if q['topic'])
    chapter_counts=Counter(c for q in questions for c in q['chapters'])
    order=CHAPTERS+[c for c in chapter_counts if c not in CHAPTERS]
    chapters=[{'chapter':c,'question_count':chapter_counts[c]} for c in order if chapter_counts[c]]
    meta={'schema_version':2,'sources':sources,'systems':SYSTEMS,
          'subjects':[{'subject':s,'question_count':n} for s,n in Counter(q['subject'] for q in questions).items()],
          'topics':[{'topic':s,'question_count':n} for s,n in topics.items()], 'chapters':chapters,
          'types':TYPE_NAMES,'counts':dict(Counter(q['answer_status'] for q in questions))}
    return {'meta':meta,'questions':questions}


def matches(q,params):
    one=lambda k:params.get(k,[''])[0]
    for key,column in [('subject','subject'),('topic','topic'),('chapter','chapter'),('type','question_type'),('status','answer_status')]:
        value=one(key)
        if value and value!='all':
            if key=='chapter':
                if value=='未分类':
                    if q['chapters']:return False
                elif value not in q['chapters']:return False
            elif q.get(column)!=value:return False
    source=one('source')
    if source and source!='all' and source not in {str(i) for i in q['source_ids']}:return False
    system=one('system')
    if system in SYSTEMS and q['topic'] not in SYSTEMS[system]:return False
    search=one('q').strip().lower()
    if search and search not in ' '.join([q['question_text'],q.get('topic') or '',*q['chapters'],*[o['text'] for o in q['options']]]).lower():return False
    return True
