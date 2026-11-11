"""Export the shared quiz data contract for GitHub Pages."""
import json
import sys
from pathlib import Path
from quiz_data import build_payload

def main():
    if len(sys.argv)!=3:raise SystemExit('Usage: python build_data.py DATABASE.sqlite OUTPUT.json')
    payload=build_payload(sys.argv[1])
    out=Path(sys.argv[2]);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    print(f'Exported {len(payload["questions"])} questions to {out}')

if __name__=='__main__':main()
