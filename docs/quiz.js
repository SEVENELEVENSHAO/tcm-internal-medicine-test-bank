'use strict';
const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const statusNames = {source_answer_present:'有答案依据', needs_review:'待核对 · 不判分', not_in_source:'尚无可确认答案'};
function readStored(key, fallback) {
  try { return JSON.parse(localStorage.getItem(key) || 'null') ?? fallback; } catch { return fallback; }
}
function persist(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { $('statusbar').textContent = '浏览器未允许保存进度，本次仍可继续练习。'; }
}
const storedAnswered = readStored('tcm-answered', []);
const state = {all:[], questions:[], index:0, meta:null, staticMode:false,
  selected:new Set(), revealed:null, draft:'', answered:new Set(Array.isArray(storedAnswered) ? storedAnswered : [])};
const current = () => state.questions[state.index];
const subjectRows = () => state.all.filter(q => $('subject').value === 'all' || q.subject === $('subject').value);
const optionFor = (value, label) => '<option value="' + esc(value) + '">' + esc(label) + '</option>';
function fillSelect(id, first, entries) {
  const value = $(id).value;
  $(id).innerHTML = optionFor(id === 'source' ? 'all' : '', first) + entries.map(e => optionFor(e.value, e.label)).join('');
  if ([...$(id).options].some(o => o.value === value)) $(id).value = value;
}
function syncFilters() {
  const subject = $('subject').value, rows = subjectRows(), ids = new Set(rows.flatMap(q => q.source_ids));
  $('chapterField').hidden = subject !== '金匮要略';
  $('systemField').hidden = $('topicField').hidden = subject !== '中医内科';
  fillSelect('source', '全部来源', state.meta.sources.filter(s => ids.has(s.id)).map(s => ({value:s.id, label:s.filename + ' (' + rows.filter(q => q.source_ids.includes(s.id)).length + ')'})));
  const kinds = [...new Set(rows.map(q => q.question_type).filter(Boolean))];
  fillSelect('questionType', '全部题型', kinds.map(t => ({value:t, label:(state.meta.types[t] || t) + ' (' + rows.filter(q => q.question_type === t).length + ')'})));
  const chapters = state.meta.chapters.map(c => ({value:c.chapter, label:c.chapter + ' (' + rows.filter(q => q.chapters.includes(c.chapter)).length + ')'}));
  chapters.push({value:'未分类', label:'未分类 (' + rows.filter(q => !q.chapters.length).length + ')'});
  fillSelect('chapter', '全部篇章', chapters);
  const topics = state.meta.systems[$('system').value];
  fillSelect('topic', '全部专题', state.meta.topics.filter(t => !topics || topics.includes(t.topic)).map(t => ({value:t.topic, label:t.topic + ' (' + t.question_count + ')'})));
  $('subjectName').textContent = subject === 'all' ? '全部科目' : subject + ' · 学习模式';
  const counts = rows.reduce((out,q) => (out[q.answer_status] = (out[q.answer_status] || 0) + 1, out), {});
  $('answerCounts').textContent = '有答案依据 ' + (counts.source_answer_present || 0) + ' · 待核对 ' + (counts.needs_review || 0) + ' · 尚无答案 ' + (counts.not_in_source || 0);
}
function loadQuestions() {
  const subject = $('subject').value, source = $('source').value, chapter = $('chapter').value;
  const type = $('questionType').value, status = $('answerStatus').value, topic = $('topic').value;
  const systemTopics = subject === '中医内科' ? state.meta.systems[$('system').value] : null;
  const search = $('search').value.trim().toLocaleLowerCase();
  state.questions = state.all.filter(q =>
    (subject === 'all' || q.subject === subject) &&
    (source === 'all' || q.source_ids.includes(Number(source))) &&
    (subject !== '金匮要略' || !chapter || (chapter === '未分类' ? !q.chapters.length : q.chapters.includes(chapter))) &&
    (subject !== '中医内科' || ((!topic || q.topic === topic) && (!systemTopics || systemTopics.includes(q.topic)))) &&
    (!type || q.question_type === type) && (!status || q.answer_status === status) &&
    (!search || [q.question_text, q.group_context, q.topic, ...q.chapters, ...q.options.map(o => o.text)].join(' ').toLocaleLowerCase().includes(search)) &&
    (!$('unansweredOnly').checked || !state.answered.has(q.id)));
  state.index = 0; resetAnswer(); render(); $('statusbar').textContent = '';
}
function resetAnswer() { state.selected = new Set(); state.revealed = null; state.draft = ''; }
function gradeFor(answer) {
  if (!answer?.answer_key || answer.answer_status !== 'source_answer_present') return null;
  const key = new Set(answer.answer_key);
  return key.size === state.selected.size && [...key].every(l => state.selected.has(l));
}
function sourceLabel(s) {
  return s.source_name + ' · ' + (s.chapter ? s.chapter + ' · ' : '') + (s.locator || (s.source_page ? 'PDF第' + s.source_page + '页' : '原文第' + s.item_number + '题'));
}
function render() {
  const q = current();
  $('resultCount').textContent = state.questions.length.toLocaleString() + ' 道题符合筛选';
  for (const id of ['previous','next','nextTop','shuffle']) $(id).disabled = !q;
  if (!q) {
    $('questionRegion').innerHTML = '<div class="empty">当前筛选下没有题目。请调整来源、篇章或题型。</div>';
    $('position').textContent = ''; return;
  }
  $('previous').disabled = state.index === 0;
  $('next').disabled = $('nextTop').disabled = state.index === state.questions.length - 1;
  const multi = q.question_type === 'Multiple', reveal = state.revealed;
  const grade = gradeFor(reveal), key = new Set(reveal?.answer_key || '');
  const tagclass = q.answer_status === 'needs_review' ? 'review' : q.answer_status === 'not_in_source' ? 'none' : '';
  let body = '';
  if (q.options.length) {
    body = '<div class="sub selection-hint">' + (multi ? '多项选择 · 可选多项' : '单项选择') + '</div><div class="choices">' + q.options.map((o,i) => {
      const selected = state.selected.has(o.letter);
      let cls = selected ? 'selected ' : '';
      if (reveal && key.size) cls += key.has(o.letter) ? 'correct ' : selected ? 'incorrect ' : '';
      return '<button type="button" class="choice ' + cls + (multi ? 'multi-choice' : '') + '" aria-pressed="' + selected + '" data-option="' + i + '" ' + (reveal ? 'disabled' : '') + '><span class="choice-letter">' + esc(o.letter) + '</span><span>' + esc(o.text) + '</span></button>';
    }).join('') + '</div>';
  } else {
    body = '<label class="draft-label" for="draft">自行作答（可选）</label><textarea id="draft" rows="4" placeholder="先写下思路，再核对参考答案">' + esc(state.draft) + '</textarea><div class="sub">本题不自动判分，可对照原文答案自行核对。</div>';
  }
  let answer = '';
  if (reveal) {
    const result = grade === null ? '本题不自动判分' : grade ? '回答正确' : '回答不正确';
    const evidence = (reveal.evidence || []).map(e => '<div class="evidence-entry"><div>' + esc(e.source_name || '原文依据') + (e.source_page ? ' · PDF第' + esc(e.source_page) + '页' : '') + '</div><div class="answer-text">' + esc(e.evidence_text) + '</div></div>').join('');
    answer = '<div class="answer ' + tagclass + '"><div class="answer-title">' + result + '</div>' +
      (grade !== null ? '<div class="sub">你的选择 ' + esc([...state.selected].sort().join('')) + ' · 原文答案 ' + esc(reveal.answer_key) + '</div>' : '') +
      '<div class="answer-text">' + esc(reveal.answer_text || (q.answer_status === 'needs_review' ? '尚无可确认的答案，请对照来源核实。' : '原资料中尚未匹配到可确认的答案。')) + '</div>' +
      (q.answer_status === 'needs_review' ? '<div class="sub">需核对：' + esc(q.extraction_status) + '</div>' : '') +
      (evidence ? '<details class="evidence"><summary>查看答案原文依据（' + (reveal.evidence || []).length + '）</summary>' + evidence + '</details>' : '') + '</div>';
  }
  const sources = q.sources || [];
  const provenance = sources.length > 1 ? '<details class="source"><summary>来源：' + esc(sourceLabel(sources[0])) + ' · 共 ' + sources.length + ' 处记录</summary>' + sources.slice(1).map(s => '<div>' + esc(sourceLabel(s)) + '</div>').join('') + '</details>' : '<div class="source">来源：' + esc(sourceLabel(sources[0])) + '</div>';
  $('questionRegion').innerHTML = '<article class="question"><div class="qmeta"><span class="tag">' + esc(q.subject) + '</span><span class="tag type">' + esc(q.chapters[0] || q.topic || '未分类') + '</span><span class="tag type">' + esc(state.meta.types[q.question_type] || q.question_type || '问答 / 原文题') + '</span><span class="tag status ' + tagclass + '">' + esc(statusNames[q.answer_status]) + '</span></div>' +
    (q.group_context ? '<div class="group-context"><div class="sub">共用题干 / 题组说明</div>' + esc(q.group_context) + '</div>' : '') +
    '<p class="qtext">' + esc(q.question_text) + '</p>' + body + answer + provenance + '</article><div class="answer-control"><button class="button ' + (reveal ? '' : 'primary') + '" id="toggleAnswer">' + (reveal ? '收起答案' : q.options.length && q.answer_status === 'source_answer_present' ? '提交并查看答案' : '查看参考答案') + '</button></div>';
  $('questionRegion').querySelectorAll('[data-option]').forEach(button => button.addEventListener('click', () => {
    const letter = q.options[Number(button.dataset.option)].letter;
    if (multi) state.selected.has(letter) ? state.selected.delete(letter) : state.selected.add(letter);
    else state.selected = new Set([letter]);
    render();
  }));
  $('draft')?.addEventListener('input', event => { state.draft = event.target.value; });
  $('toggleAnswer').addEventListener('click', toggleAnswer);
  $('position').textContent = '第 ' + (state.index + 1).toLocaleString() + ' / ' + state.questions.length.toLocaleString() + ' 题' + (state.answered.has(q.id) ? ' · 已作答 / 核对' : '');
}
async function toggleAnswer() {
  if (state.revealed) { state.revealed = null; render(); return; }
  const q = current();
  if (q.options.length && q.answer_status === 'source_answer_present' && !state.selected.size) {
    $('statusbar').textContent = '请先选择答案，再提交核对。'; return;
  }
  const button = $('toggleAnswer'); button.disabled = true; button.textContent = '正在读取答案…';
  try {
    const answer = state.staticMode ? q : await fetchJson('/api/questions/' + q.id + '/answer');
    if (current()?.id !== q.id) return;
    state.revealed = answer; state.answered.add(q.id);
    persist('tcm-answered', [...state.answered]);
    const grade = gradeFor(answer);
    $('statusbar').textContent = grade === null ? '已展开原文参考答案，本题不判分。' : grade ? '回答正确。' : '回答不正确，请核对原文答案。';
    render();
  } catch {
    button.disabled = false; button.textContent = '重新读取答案';
    $('statusbar').textContent = '答案读取失败，请重试。';
  }
}
function move(step) {
  if (!state.questions.length) return;
  state.index = Math.max(0, Math.min(state.questions.length - 1, state.index + step));
  resetAnswer(); render(); $('statusbar').textContent = '';
}
async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error('HTTP ' + response.status);
  return response.json();
}
async function init() {
  try {
    let data;
    try {
      if (document.documentElement.dataset.api !== 'local') throw new Error('Static quiz');
      state.meta = await fetchJson('/api/meta');
      data = [];
      for (let offset = 0; ; offset += 500) {
        const page = await fetchJson('/api/questions?limit=500&offset=' + offset);
        data.push(...page.questions);
        if (data.length >= page.total) break;
        if (!page.questions.length) throw new Error('Incomplete question response');
      }
    } catch {
      const payload = await fetchJson('./data/questions.json');
      state.meta = payload.meta; data = payload.questions; state.staticMode = true;
    }
    state.all = data;
    $('subject').insertAdjacentHTML('beforeend', state.meta.subjects.map(s => optionFor(s.subject, s.subject + ' (' + s.question_count + ')')).join(''));
    const stored = readStored('tcm-subject', '金匮要略');
    $('subject').value = [...$('subject').options].some(o => o.value === stored) ? stored : '金匮要略';
    $('system').insertAdjacentHTML('beforeend', Object.keys(state.meta.systems).map(n => optionFor(n,n)).join(''));
    $('databaseCount').textContent = data.length.toLocaleString() + ' 道题 · ' + state.meta.subjects.length + ' 门科目';
    syncFilters();
    for (const id of ['subject','source','chapter','system','topic','questionType','answerStatus','unansweredOnly']) {
      $(id).addEventListener('change', () => {
        if (id === 'subject') {
          for (const f of ['source','chapter','system','topic','questionType','answerStatus']) $(f).value = f === 'source' ? 'all' : '';
          persist('tcm-subject', $('subject').value); syncFilters();
        }
        if (id === 'system') { $('topic').value = ''; syncFilters(); }
        loadQuestions();
      });
    }
    let timer;
    $('search').addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(loadQuestions,180); });
    $('previous').addEventListener('click', () => move(-1));
    $('next').addEventListener('click', () => move(1));
    $('nextTop').addEventListener('click', () => move(1));
    $('shuffle').addEventListener('click', () => {
      if (!state.questions.length) return;
      state.index = Math.floor(Math.random() * state.questions.length); resetAnswer(); render();
    });
    document.addEventListener('keydown', event => {
      if (/INPUT|TEXTAREA|SELECT|BUTTON/.test(event.target.tagName) || event.ctrlKey || event.altKey || event.metaKey) return;
      if (event.key === 'ArrowRight') move(1);
      if (event.key === 'ArrowLeft') move(-1);
    });
    loadQuestions();
  } catch {
    $('databaseCount').textContent = '题库读取失败';
    $('questionRegion').innerHTML = '<div class="error">题库读取失败，请检查网络后刷新页面。</div>';
  }
}
init();
