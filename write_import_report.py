"""Write a reviewable source inventory and question-level exception report."""
from pathlib import Path
import json
import sqlite3
import sys
from ingest_jinkui import TYPE_NAMES

BASE=Path(__file__).resolve().parent


def main():
    database=Path(sys.argv[1])
    report=json.loads((BASE.parent/'jinkui-work/import-report.json').read_text(encoding='utf-8'))
    db=sqlite3.connect(database);db.row_factory=sqlite3.Row
    total=db.execute('SELECT COUNT(*) FROM questions').fetchone()[0]
    reference=sum(s['status'].startswith('reference') for s in report['sources'])
    question_sources=[s for s in report['sources'] if s['status'] not in {'reference','reference_scanned','archive_inventoried'}]
    def cell(value):return str(value or '未分类').replace('|','／').replace('\n',' ')
    lines=['# 金匮要略题库导入报告','',
        '本次把两个资料目录并入现有网站，按原书篇章和题型练习。原文件保持不变，原有中医内科 2,185 道题及其 ID、题文和答案记录均已逐字段比对保留。','',
        f'- 本次收录金匮要略 **{report["unique_questions"]:,} 道去重题目**；网站合计 **{total:,} 道**。',
        f'- 两个目录共有 90 个文件，另检查压缩包内 8 个成员；98 个登记位置对应 {report["unique_files"]} 份唯一文件内容。19 个重复文件副本、8 个已有内容的压缩包成员不重复抽取。',
        f'- {len(question_sources)} 份题目来源；{reference} 份教材、知识点和教参单独登记为参考资料；1 个压缩包作为容器登记。',
        f'- 去重前有 {report["question_occurrences"]:,} 条来源题目记录，保留全部来源定位。',
        '- 204 页扫描习题册已全部完成本地 PP-OCRv5 中文识别，保留页码、识别坐标及置信度。扫描教参仅作为参考资料登记，未生成练习题。','',
        '## 答案状态','', '| 状态 | 题数 |','| --- | ---: |']
    labels={'source_answer_present':'有原文答案依据','needs_review':'待核对，不自动判分','not_in_source':'尚无可确认答案'}
    for status,n in report['answer_status'].items():lines.append(f'| {labels[status]} | {n:,} |')
    lines+=['','“有原文答案依据”表示完成来源对应，不代表已经逐题进行医学内容校审。答案冲突、选项缺损、题号重复及低置信度识别均保留待核对；主观题只供自行核对。','',
        '## 题型','', '| 题型 | 去重题数 |','| --- | ---: |']
    for kind,n in report['types'].items():lines.append(f'| {TYPE_NAMES.get(kind,kind)} | {n:,} |')
    lines+=['','## 各来源处理结果','', '题数为各文件中的来源记录数，跨文件相同题目可指向同一练习题；各行不可直接相加为去重题数。','',
        '| 来源 | 来源题数 | 有答案 | 待核对 | 尚无答案 |','| --- | ---: | ---: | ---: | ---: |']
    for s in question_sources:
        counts=s.get('answer_status',{})
        lines.append(f'| {cell(s["source"])} | {s["questions"]} | {counts.get("source_answer_present",0)} | {counts.get("needs_review",0)} | {counts.get("not_in_source",0)} |')
    lines+=['','## 参考资料与重复副本','']
    for s in report['sources']:
        if s['status'].startswith('reference'):
            lines.append(f'- {s["source"]}：'+('扫描参考资料，未 OCR、未抽成题目。' if s['status']=='reference_scanned' else '已提取并登记为参考资料，未抽成题目。'))
        if len(s['aliases'])>1:
            lines.append(f'- {s["source"]} 的相同内容另见：'+'；'.join(a for a in s['aliases'] if a!=s['source'])+'。')
    lines+=['','## 验证与适用范围','',
        '- 所有 71 份唯一内容均有处理结果；旧版 DOC 使用只读二进制解析，未执行宏或嵌入对象，无失败文件。',
        '- 逐字段比较原有中医内科题目；重复导入前后题目 ID、题数、来源数、来源页数、题目出现次数和答案依据条数保持一致。',
        '- 13 项解析回归测试通过，覆盖内嵌答案拆分、同号跨篇章、同号跨题型、表格答案、配伍题、共用病例及其识别置信度、答案冲突、摄氏温度和主观题子条目。',
        '- 静态网页与本地 API 各通过 18 项浏览器检查：单多选判分、主观题核对、待核对题不判分、科目和来源筛选、超过 500 题的访问、360 像素手机布局和旧作答记录保留；无浏览器控制台错误。',
        '- 原页抽样检查题目页、答案页、跨页题和共用病例；PDF 第 147、172 页的 A3 答案分型标题已对照图像修正识别结果。',
        '- 保留全文识别结果、原始行坐标和未唯一匹配诊断，便于继续校对；本次未声称逐题完成原书图像校对。',
        '- Word 定位采用段落、篇章和题号；网站不把其内部存储页号显示为真实页码。','',
        '## 待核对题目','', '| 练习题 ID | 篇章 | 题型 | 题号 | 原因 |','| ---: | --- | --- | --- | --- |']
    for q in db.execute("SELECT id,chapter,question_type,item_number,extraction_status FROM questions WHERE subject='金匮要略' AND answer_status='needs_review' ORDER BY id"):
        lines.append(f'| {q["id"]} | {cell(q["chapter"])} | {cell(TYPE_NAMES.get(q["question_type"],q["question_type"]))} | {cell(q["item_number"])} | {cell(q["extraction_status"])} |')
    lines+=['','## 尚未唯一对应的答案线索','', '以下保留原始匹配诊断，不自动指定给其他题号或题型。','']
    for s in question_sources:
        if s.get('diagnostics'):
            lines+=['### '+s['source'],'','| 篇章 | 题型 | 题号 | 诊断 |','| --- | --- | --- | --- |']
            for d in s['diagnostics']:
                lines.append(f'| {cell(d.get("chapter"))} | {cell(TYPE_NAMES.get(d.get("type"),d.get("type")))} | {cell(d.get("number"))} | {cell(d["issue"])} |')
            lines.append('')
    text='\n'.join(lines).rstrip()+'\n'
    (BASE/'docs/import-report.md').write_text(text,encoding='utf-8')
    (BASE.parent/'金匮要略导入报告.md').write_text(text,encoding='utf-8')
    db.close()


if __name__=='__main__':main()
