#!/usr/bin/env python3
"""
data/quizzes/*.js 파일 목록을 스캔해 index.html의
<!-- QUIZ_SCRIPTS_START --> ~ <!-- QUIZ_SCRIPTS_END --> 마커 사이를
<script src="data/quizzes/...js"></script> 줄들로 자동 갱신한다.

사용법:
    python3 tools/update-index.py
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(ROOT, 'index.html')
QUIZ_DIR = os.path.join(ROOT, 'data', 'quizzes')

START = '<!-- QUIZ_SCRIPTS_START -->'
END = '<!-- QUIZ_SCRIPTS_END -->'

# 회차 정렬 우선순위 — 그림문제 → 이론 → 실기 → 나머지(가나다)
GROUP_ORDER = ['그림문제', '이론', '실기']


def sort_key(name: str):
    base = name[:-3] if name.endswith('.js') else name
    for i, g in enumerate(GROUP_ORDER):
        if base.startswith(g):
            return (i, base)
    return (len(GROUP_ORDER), base)


def main():
    if not os.path.isdir(QUIZ_DIR):
        sys.exit(f'not found: {QUIZ_DIR}')

    files = sorted(
        [f for f in os.listdir(QUIZ_DIR) if f.endswith('.js')],
        key=sort_key,
    )
    if not files:
        sys.exit(f'no quiz files in {QUIZ_DIR}')

    tags = '\n'.join(f'    <script src="data/quizzes/{f}"></script>' for f in files)
    block = f'{START}\n{tags}\n    {END}'

    with open(INDEX, 'r', encoding='utf-8') as fh:
        html = fh.read()

    pattern = re.compile(re.escape(START) + r'.*?' + re.escape(END), re.DOTALL)
    if not pattern.search(html):
        sys.exit(f'markers not found in {INDEX}. 추가 필요: {START} ... {END}')

    new_html = pattern.sub(block, html)
    if new_html == html:
        print(f'no changes ({len(files)} quiz files)')
        return

    with open(INDEX, 'w', encoding='utf-8') as fh:
        fh.write(new_html)
    print(f'updated {INDEX} with {len(files)} <script> tags')


if __name__ == '__main__':
    main()
