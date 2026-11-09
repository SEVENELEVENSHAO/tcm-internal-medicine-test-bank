# TCM Internal Medicine Quiz

Static GitHub Pages quiz interface for the OCR-assembled TCM internal medicine test bank. The site supports organ-system and topic filters, answer-status filters, question search, single-choice and multi-select practice, and answer evidence.

## Deployment

GitHub Pages publishes the docs/ directory from the main branch. The browser loads docs/data/questions.json; the local Python API and SQLite database are not required on the hosted site.

## Data

The deployed snapshot contains 2,185 extracted questions from 10 indexed sources, including OCR-derived question text, answer keys, and source-page evidence. Original PDFs and the assembled SQLite database are not included. OCR and answer matching can contain errors. This material is published for study; redistribution rights for the source materials have not been independently established.

To regenerate the JSON from a local test_bank.sqlite, run: python build_data.py PATH_TO_DATABASE docs/data/questions.json.
