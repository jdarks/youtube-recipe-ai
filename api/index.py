import os
# Python 3.14 등에서 protobuf 라이브러리 충돌 (TypeError)을 방지하는 설정
os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"

from flask import Flask, jsonify, request, render_template_string
from youtube_transcript_api import YouTubeTranscriptApi
import requests
import re

app = Flask(__name__)

# Vercel 환경 변수에 GEMINI_API_KEY를 등록해야 작동합니다. (GitHub에는 절대 키를 올리지 마세요!)
API_KEY = os.environ.get("GEMINI_API_KEY")

def extract_video_id(url):
    # 유튜브 URL에서 11자리 비디오 ID만 정규식으로 추출
    pattern = r'(?:https?:\/\/)?(?:www\.)?(?:youtube\.com\/(?:[^\/\n\s]+\/\S+\/|(?:v|e(?:mbed)?)\/|\S*?[?&]v=)|youtu\.be\/)([a-zA-Z0-9_-]{11})'
    match = re.search(pattern, url)
    return match.group(1) if match else None

def get_youtube_transcript(video_id):
    try:
        # 우선 한국어 자막 시도, 없으면 기본 생성 자막에서 텍스트 합치기
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['ko', 'en'])
        text = " ".join([t['text'] for t in transcript_list])
        return text
    except Exception as e:
        return None

def analyze_recipe(transcript_text):
    if not API_KEY:
        return {"success": False, "error": "Google Gemini API 키가 설정되지 않았습니다."}
    
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={API_KEY}"
        headers = {'Content-Type': 'application/json'}
        
        # 프롬프트(명령어): 이 부분이 NotebookLM 역할의 핵심입니다.
        prompt = f"""
        다음은 요리 유튜브 영상의 음성 자막입니다. 
        이 자막을 분석하여 다음의 '요리 레시피 정보'를 마크다운(Markdown) 포맷으로 보기 좋게 정리해주세요.
        
        1. 요리 이름 (영상을 보고 추측해서 멋지게 지어주세요)
        2. 요리 재료 목록 (수량이나 비율이 언급되었다면 포함)
        3. 요리 순서 (불의 강도, 조리 시간, 핵심 팁 등 구체적인 정보 포함)
        
        자막 텍스트:
        {transcript_text}
        """
        
        data = {
            "contents": [{
                "parts": [{"text": prompt}]
            }]
        }
        
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        
        result_json = response.json()
        recipe_text = result_json['candidates'][0]['content']['parts'][0]['text']
        
        return {"success": True, "recipe": recipe_text}
    except Exception as e:
        return {"success": False, "error": str(e)}

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>유튜브 AI 레시피 추출기</title>
    <!-- 마크다운 변환 라이브러리 추가 -->
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; background-color: #f7f9fc; color: #333; margin: 0; padding: 40px 20px; display: flex; justify-content: center; }
        .card { background: white; padding: 40px; border-radius: 16px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); width: 100%; max-width: 700px; }
        h1 { color: #2c3e50; font-size: 26px; margin-bottom: 24px; text-align: center; }
        .search-box { display: flex; gap: 10px; margin-bottom: 20px; }
        input { flex: 1; padding: 14px; border: 1px solid #ddd; border-radius: 8px; font-size: 16px; outline: none; transition: border-color 0.3s; }
        input:focus { border-color: #3498db; }
        button { padding: 14px 24px; background-color: #2c3e50; color: white; border: none; border-radius: 8px; font-size: 16px; cursor: pointer; transition: background-color 0.3s; white-space: nowrap; }
        button:hover { background-color: #1a252f; }
        .loading { display: none; text-align: center; color: #7f8c8d; margin: 20px 0; font-weight: 500; }
        .error { color: #e74c3c; background: #fadbd8; padding: 12px; border-radius: 8px; font-size: 14px; margin-bottom: 20px; text-align: center; }
        .result-box { margin-top: 30px; line-height: 1.8; color: #444; background-color: #fcfcfc; padding: 30px; border-radius: 12px; border: 1px solid #eee; }
        .result-box h2, .result-box h3 { color: #2c3e50; margin-top: 0; }
        .footer { margin-top: 40px; font-size: 13px; color: #aaa; text-align: center; }
    </style>
</head>
<body>
    <div class="card">
        <h1>🍳 유튜브 영상 → 레시피 AI 추출기</h1>
        
        <form class="search-box" method="GET" action="/">
            <input type="url" name="url" placeholder="유튜브 요리 영상 링크 붙여넣기 (예: https://youtu.be/...)" value="{{ url or '' }}" required>
            <button type="submit" onclick="document.getElementById('loading').style.display='block';">AI 분석 시작</button>
        </form>

        <div id="loading" class="loading">⏳ 자막을 모으고 AI 요리사가 레시피를 분석 중입니다... (10~20초 소요)</div>

        {% if error %}
            <div class="error">
                <strong>오류 안내:</strong> {{ error }}
            </div>
        {% endif %}

        {% if recipe %}
            <div class="result-box" id="recipe-content"></div>
            <script>
                // 서버에서 받은 마크다운 텍스트를 HTML로 예쁘게 렌더링
                const rawMarkdown = `{{ recipe.replace('`', '\\`').replace('\\n', '\\\\n') | safe }}`;
                document.getElementById('recipe-content').innerHTML = marked.parse(rawMarkdown);
            </script>
        {% endif %}
        
        <div class="footer">Gemini AI x YouTube Transcript API | Vercel Serverless</div>
    </div>
</body>
</html>
"""

@app.route('/')
def home():
    url = request.args.get('url')
    if not url:
        return render_template_string(HTML_TEMPLATE)
    
    video_id = extract_video_id(url)
    if not video_id:
        return render_template_string(HTML_TEMPLATE, url=url, error="유효한 유튜브 링크가 아닙니다. 링크를 다시 확인해주세요.")
        
    transcript = get_youtube_transcript(video_id)
    if not transcript:
        return render_template_string(HTML_TEMPLATE, url=url, error="이 영상에서 자막을 가져올 수 없습니다. 쇼츠나 자막(CC)이 아예 없는 영상일 수 있습니다.")
        
    result = analyze_recipe(transcript)
    if result["success"]:
        return render_template_string(HTML_TEMPLATE, url=url, recipe=result["recipe"])
    else:
        return render_template_string(HTML_TEMPLATE, url=url, error=f"AI 분석 실패: {result['error']}")

if __name__ == '__main__':
    app.run(debug=True)
