# 中医题库

同一个 GitHub Pages 网站提供中医内科和金匮要略练习。支持科目、篇章、系统、病证专题、题型、来源、答案状态和关键词筛选。

## 数据与练习

当前共 7,969 道题：中医内科 2,185 道，金匮要略去重后 5,784 道。金匮要略有 5,398 道具备原文答案依据，341 道待核对，45 道尚无可确认答案。单选正常判分、多选按完整集合判分；主观题、待核对题及未确认答案的题目供自行核对。

题干内嵌答案已拆开保存；共用病例与配伍选项随题展示。相同题目保留多个来源，选项不同的题目分别保留。Word 来源采用段落定位，PDF 来源保留原始 PDF 页码。原有中医内科 ID 和浏览器 `tcm-answered` 记录保持兼容。筛选结果不再截断为前 500 道。

查看 [金匮资料导入报告](docs/import-report.md)，了解各来源题数、参考资料、重复副本及待核对项目。原始 DOC、DOCX、PDF 和 SQLite 数据库不上传到此仓库。OCR 和原书答案本身可能有错误；答案依据不等同于逐题医学内容校审。原资料的再分发权利未独立核实。

## 本地服务与发布

GitHub Pages 继续发布 `main:/docs`。入口为 `docs/index.html`，加载 `docs/data/questions.json`，不依赖本地 API。

在原工作区中运行 `python app.py`，本地网址为 `http://127.0.0.1:8765`。服务使用本仓库的 `local_server.py`、`quiz_data.py` 和同一份网页；问题列表不返回答案，提交后由答案接口返回。

重新导出：

```text
python build_data.py PATH_TO_DATABASE docs/data/questions.json
```

## 金匮导入流程

以下命令在原工作区布局下使用，缓存写入仓库同级的 `jinkui-work`，原始文件只读：

```text
python extract_sources.py
python ocr_sources.py PATH_TO_SCANNED_WORKBOOK.pdf
python ingest_jinkui.py --database PATH_TO_DATABASE
python build_data.py PATH_TO_DATABASE docs/data/questions.json
python write_import_report.py PATH_TO_DATABASE
```

提取普通文件使用 `requirements-import.txt`。旧版 Word 按 MS-DOC piece table 提取，不执行宏。OCR 命令使用已有的 PaddleOCR 3.5 环境，所有 204 页的结果均可续跑；模型初始化和原始坐标只保存在本地缓存。教材、教参和知识点资料只登记为参考来源。导入按文件哈希和题目内容识别重复，保留原有 ID；重复导入不会新增题目或来源记录。旧的破坏性数据库构建器已在本地增加保护，遇到新增科目时拒绝覆盖。

数据库接口新增 `subject`、`chapter`、`options_json`、`group_context`、`source_locator` 和 `dedupe_key`；`question_occurrences` 保存合并题目的全部出处。静态数据版本为 `schema_version: 2`，新增结构化选项、题组信息、篇章集合、多个来源和只对可可靠判分题目提供的 `answer_key`。

## 验证

```text
python -m unittest -v test_ingestion.py
node test_ui.cjs http://127.0.0.1:8765
```

浏览器检查需要可解析到 Playwright 的 Node 环境；如已有浏览器版本不同，可用 `PLAYWRIGHT_CHROMIUM_EXECUTABLE` 指定其路径。实际验证覆盖静态网页、本地 API、手机布局、原有中医内科回归、500 题后的访问和作答记录保留。数据库还经过旧记录逐字段比对、外键检查及重复导入前后 ID 与各表条数比对。
