#!/bin/bash
# Netlify 배포용 빌드 스크립트
# docs.html 제거 + 모든 페이지에서 자료실 관련 링크 숨기기

echo "🔧 Netlify 빌드 시작..."

# 1. docs.html 삭제
rm -f docs.html
echo "  ✅ docs.html 삭제"

# 2. index.html에서 자료실 버튼 제거 (여러줄에 걸친 <a> 태그 포함)
python3 -c "
import re
with open('index.html','r') as f: h=f.read()
h=re.sub(r'<a href=\"docs\.html\"[^>]*>.*?</a>', '', h, flags=re.DOTALL)
with open('index.html','w') as f: f.write(h)
print('  ✅ index.html 자료실 링크 제거')
"

# 3. ir.html 네비게이션 바에서 자료실 링크 제거
sed -i '/<a href="docs.html"/d' ir.html
echo "  ✅ ir.html 자료실 링크 제거"

# 4. study.html 네비게이션 바에서 자료실 링크 제거
sed -i '/<a href="docs.html"/d' study.html
echo "  ✅ study.html 자료실 링크 제거"

echo "🎉 Netlify 빌드 완료 — 공개 배포판 준비됨"
