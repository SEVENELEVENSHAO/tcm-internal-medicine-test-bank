"""Behavioral checks for the source layouts that can silently mispair answers."""
import unittest
from ingest_jinkui import parse_source,resolve_answer,fingerprint,CHAPTERS


def entry(text,name='demo.doc'):
    return {'aliases':[name],'suffix':'.docx' if name.endswith('.docx') else '.doc',
            'pages':[{'number':None,'text':text}]}


class ImportTests(unittest.TestCase):
    def test_inline_key_is_hidden(self):
        questions,_=parse_source(entry('1.题干（C）\nA.甲\nB.乙\nC.丙\nD.丁\nE.戊','金匮要略单选题.docx'))
        q=questions[0]
        self.assertNotIn('(C)',q.stem)
        self.assertEqual(resolve_answer(q),('C','source_answer_present'))
        self.assertEqual(len(q.options),5)

    def test_invalid_inline_key_is_hidden_and_reviewed(self):
        q=parse_source(entry('1.题干（ABFDE）\nA.甲\nB.乙\nC.丙\nD.丁\nE.戊','金匮要略多选题.docx'))[0][0]
        self.assertNotIn('ABFDE',q.stem)
        self.assertEqual(resolve_answer(q)[1],'needs_review')

    def test_same_number_in_two_chapters_uses_own_key(self):
        text='绪言\n1.甲题\nA.甲B.乙C.丙D.丁\n痉湿暍病脉证治第二\n1.乙题\nA.甲B.乙C.丙D.丁\n附参考笞案\n绪言\n1.C\n痉湿暍病脉证治第二\n1.A'
        qs,_=parse_source(entry(text))
        self.assertEqual([resolve_answer(q)[0] for q in qs],['C','A'])
        self.assertEqual([q.chapter for q in qs],[CHAPTERS[0],CHAPTERS[2]])

    def test_word_table_keys_and_same_number_different_types(self):
        text='A1型题\n1.单选\nA.甲 B.乙 C.丙 D.丁 E.戊\nX型题\n1.多选\nA.甲 B.乙 C.丙 D.丁 E.戊\n答案：\nA1型题\n1\nC\nX型题\n1\nAB'
        qs,_=parse_source(entry(text))
        self.assertEqual([(q.kind,resolve_answer(q)[0]) for q in qs],[('A1','C'),('Multiple','AB')])

    def test_b1_pool_is_shared_across_continuous_items(self):
        text='B型题\nA.甲 B.乙 C.丙 D.丁 E.戊\n1.甲问\n2.乙问\n答案：\nB型题\n1.C 2.A'
        qs,_=parse_source(entry(text))
        self.assertEqual([len(q.options) for q in qs],[5,5])
        self.assertEqual([resolve_answer(q)[0] for q in qs],['C','A'])
        self.assertNotIn('A.甲',qs[0].stem)

    def test_common_case_is_retained(self):
        text='A3型题\n（1～2题共用题干）\n患者某某，症状如下。\n1.诊断？\nA.甲 B.乙 C.丙 D.丁 E.戊\n2.治法？\nA.甲 B.乙 C.丙 D.丁 E.戊'
        qs,_=parse_source(entry(text))
        self.assertEqual(len(qs),2)
        self.assertTrue(all('患者某某' in q.shared for q in qs))

    def test_printed_cases_without_common_case_label(self):
        text='A3型题\n张某,男,35岁。病史如下。\n1.诊断?\nA.甲 B.乙 C.丙 D.丁 E.戊\n2.治法?\nA.甲 B.乙 C.丙 D.丁 E.戊\n李某,女,30岁。另一病史。\n3.诊断?\nA.甲 B.乙 C.丙 D.丁 E.戊'
        qs,_=parse_source(entry(text))
        self.assertEqual(len(qs),3)
        self.assertTrue(all('张某' in q.shared for q in qs[:2]))
        self.assertIn('李某',qs[2].shared)
        self.assertNotIn('李某',qs[1].options[-1]['text'])

    def test_conflicting_and_duplicate_number_answers_stay_ungraded(self):
        q=parse_source(entry('1.题干\nA.甲 B.乙 C.丙 D.丁 E.戊\n【参考答案】A\n【参考答案】B'))[0][0]
        self.assertEqual(resolve_answer(q)[1],'needs_review')
        qs,_=parse_source(entry('1.甲题\nA.甲 B.乙\n1.乙题\nA.甲 B.乙\n答案：\n1.A'))
        self.assertTrue(all(resolve_answer(q)[1]=='needs_review' for q in qs))

    def test_subjective_answer_separate_from_question(self):
        qs,_=parse_source(entry('金匮要略填空题\n1.经文（）。\n原文填空答案','金匮要略填空题.docx'))
        self.assertEqual(qs[0].stem,'经文()。')
        self.assertEqual(resolve_answer(qs[0])[0],'原文填空答案')

    def test_options_and_shared_case_change_duplicate_identity(self):
        a=[{'letter':'A','text':'甲'},{'letter':'B','text':'乙'}]
        b=[{'letter':'A','text':'乙'},{'letter':'B','text':'甲'}]
        self.assertEqual(fingerprint('同题',a,'Single'),fingerprint(' 同题 ',a,'A1'))
        self.assertNotEqual(fingerprint('同题',a,'A1'),fingerprint('同题',b,'A1'))
        self.assertNotEqual(fingerprint('同题',a,'A3','病例甲'),fingerprint('同题',a,'A3','病例乙'))

    def test_answer_subpoints_are_not_new_subjective_questions(self):
        text='金匮要略简答题\n1.问题一?\n①第一点\n②第二点\n2.问题二?\n完整答案'
        qs,_=parse_source(entry(text,'金匮要略简答、论述、病例分析.docx'))
        self.assertEqual(len(qs),2)
        self.assertIn('第二点',resolve_answer(qs[0])[0])

    def test_celsius_in_case_does_not_become_an_option(self):
        text='1.患者体温38.5°C,腹痛。\nA.甲 B.乙 C.丙 D.丁 E.戊\n【参考答案】A'
        q=parse_source(entry(text))[0][0]
        self.assertIn('38.5°C',q.stem)
        self.assertEqual(len(q.options),5)

    def test_low_confidence_common_case_is_reviewed(self):
        texts=['A3型题','张某,男,35岁。病史如下。','1.诊断?', 'A.甲 B.乙 C.丙 D.丁 E.戊','【参考答案】A']
        e=entry('')
        e['pages'][0]['lines']=[{'text':t,'score':.7 if i==1 else .99,
            'box':[[0,250+i*50],[900,250+i*50],[900,280+i*50],[0,280+i*50]]} for i,t in enumerate(texts)]
        q=parse_source(e)[0][0]
        self.assertEqual(resolve_answer(q)[1],'needs_review')


if __name__=='__main__':unittest.main()
