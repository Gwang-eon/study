# 요양보호사 표준교재 파싱본

이 폴더는 `요양보호사+양성+표준교재_2024_인쇄용_compressed.pdf`를 기준으로 만든 참조 데이터셋이다.

- `index.md`: 전체 진입점
- `markdown/`: 부/장/절 기준으로 분할된 Markdown
- `pages/`: 페이지 렌더 이미지
- `figures/`: 페이지에서 자동 추출한 그림/표 후보
- `manifests/`: 페이지, 구조, 그림 후보 메타데이터
- `tools/`: 재생성 스크립트

재생성 순서:

```bash
swift -module-cache-path /private/tmp/swift-module-cache \
  textbook_reference_2024/tools/extract_textbook_pdf.swift \
  --input "./요양보호사+양성+표준교재_2024_인쇄용_compressed.pdf" \
  --output "./textbook_reference_2024" \
  --render-width 1400

python3 textbook_reference_2024/tools/build_textbook_reference.py \
  --output-dir "./textbook_reference_2024"
```

자동 추출 그림은 기준 데이터 보강용 후보이므로, 최종 정답 확정에는 페이지 이미지와 본문을 함께 대조하는 방식으로 사용한다.
