"""Resumable local PP-OCRv5 for scanned question/reference PDFs.

Run with the existing PaddleOCR-Diagram Python environment. Original PDFs are
read only; JSON caches retain every recognized line, box and confidence.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

WORK = Path(__file__).resolve().parent.parent / 'jinkui-work'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('pdf')
    parser.add_argument('--pages', default='all')
    parser.add_argument('--device', default='gpu:0')
    parser.add_argument('--refresh', action='store_true')
    args = parser.parse_args()
    os.environ.setdefault('PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK', 'True')
    sys.path.insert(0, 'D:/PaddleOCR-Diagram')
    from acupuncture_ocr import PaddleOCR
    import pypdfium2 as pdfium
    import numpy as np
    path = Path(args.pdf)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    out = WORK / 'ocr' / digest
    out.mkdir(parents=True, exist_ok=True)
    pdf = pdfium.PdfDocument(path)
    pages = range(len(pdf)) if args.pages == 'all' else [int(n) - 1 for n in args.pages.split(',')]
    pending = [i for i in pages if args.refresh or not (out / f'{i+1:04d}.json').exists()]
    if not pending:
        print('All requested pages already cached', flush=True)
        return
    pipeline = PaddleOCR(
        text_detection_model_name='PP-OCRv5_server_det',
        text_recognition_model_name='PP-OCRv5_server_rec',
        use_doc_orientation_classify=False, use_doc_unwarping=False,
        use_textline_orientation=False, return_word_box=True,
        text_det_limit_side_len=2560, text_det_limit_type='max',
        text_rec_score_thresh=.35, device=args.device)
    for i in pending:
        page = pdf[i]
        bitmap = page.render(scale=2.8)
        img = bitmap.to_pil().convert('RGB')
        result = next(iter(pipeline.predict(np.asarray(img))))
        data = result.json.get('res', result.json)
        lines = []
        for text, score, polygon in zip(data['rec_texts'], data['rec_scores'], data.get('rec_polys', data.get('dt_polys'))):
            box = [[float(pt[0]), float(pt[1])] for pt in polygon]
            lines.append({'text': str(text), 'score': float(score), 'box': box})
        # These scanned books are single column; preserve visual row order,
        # using x to order separately detected fragments of the same row.
        lines.sort(key=lambda r: (round(min(pt[1] for pt in r['box']) / 12), min(pt[0] for pt in r['box'])))
        payload = {'number': i + 1, 'text': '\n'.join(r['text'] for r in lines), 'lines': lines, 'method': 'local PP-OCRv5 upright'}
        temp = out / f'{i+1:04d}.tmp'
        temp.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
        temp.replace(out / f'{i+1:04d}.json')
        print(f'OCR {i+1}/{len(pdf)}: {len(lines)} lines', flush=True)
        img.close()
        bitmap.close()
        page.close()
    pdf.close()


if __name__ == '__main__':
    main()
