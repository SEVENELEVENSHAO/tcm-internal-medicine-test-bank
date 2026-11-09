import json
import sqlite3
import sys
from pathlib import Path

SYSTEMS = {
    "肺系": ["感冒", "咳嗽", "哮病", "喘证", "肺痈", "肺痨", "肺胀", "肺痿", "痰饮"],
    "心脑系": ["心悸", "胸痹心痛", "心衰", "不寐", "头痛", "眩晕", "中风", "痴呆", "癫狂", "痫病"],
    "脾胃系": ["胃痛", "痞满", "呕吐", "噎膈", "呃逆", "腹痛", "泄泻", "痢疾", "便秘"],
    "肝胆系": ["胁痛", "黄疸", "积聚", "鼓胀", "瘿病", "疟疾", "郁证"],
    "肾与膀胱系": ["水肿", "淋证", "癃闭", "关格", "阳痿", "腰痛"],
    "气血津液与杂病": ["血证", "消渴", "汗证", "内伤发热", "厥证", "虚劳", "肥胖"],
    "经络肢体系": ["痹证", "痉证", "痿证", "颤证"],
}

def main():
    if len(sys.argv) != 3:
        raise SystemExit("Usage: python build_data.py DATABASE.sqlite OUTPUT.json")
    db = sqlite3.connect(f"file:{Path(sys.argv[1]).resolve()}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    questions = [dict(row) for row in db.execute(
        "SELECT q.id,q.source_id,q.item_number,q.question_text,q.answer_text,q.answer_status,q.topic,q.question_type,q.extraction_status,s.filename source_name,p.page_number source_page FROM questions q JOIN sources s ON s.id=q.source_id JOIN source_pages p ON p.id=q.page_id ORDER BY q.id"
    )]
    evidence = {}
    for row in db.execute("SELECT e.question_id,e.evidence_text,e.confidence,p.page_number answer_page FROM answer_evidence e LEFT JOIN source_pages p ON p.id=e.source_page_id ORDER BY e.id"):
        evidence.setdefault(row["question_id"], []).append(dict(row))
    for question in questions:
        refs = evidence.get(question["id"], [])
        question["evidence_text"] = "\n".join(item["evidence_text"] for item in refs if item["evidence_text"]) or None
        question["confidence"] = refs[0]["confidence"] if refs else None
        pages = [str(item["answer_page"]) for item in refs if item["answer_page"] is not None]
        question["answer_page"] = ", ".join(pages) or None
    sources = [dict(row) for row in db.execute("SELECT s.id,s.filename,s.role,COUNT(q.id) question_count FROM sources s LEFT JOIN questions q ON q.source_id=s.id WHERE s.role='test_bank' GROUP BY s.id ORDER BY s.id")]
    topics = [dict(row) for row in db.execute("SELECT topic,COUNT(*) question_count FROM questions WHERE topic IS NOT NULL GROUP BY topic ORDER BY MIN(id)")]
    counts = {row["answer_status"]: row["n"] for row in db.execute("SELECT answer_status,COUNT(*) n FROM questions GROUP BY answer_status")}
    db.close()
    output = Path(sys.argv[2])
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {"meta": {"sources": sources, "topics": topics, "systems": SYSTEMS, "counts": counts}, "questions": questions}
    output.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Exported {len(questions)} questions to {output}")

if __name__ == "__main__":
    main()
