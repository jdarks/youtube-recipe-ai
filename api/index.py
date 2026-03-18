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
    # 유튜브 일반 링크, 모바일, 쇼츠(Shorts), 공유 링크 등 모든 형태 지원
    pattern = r'(?:https?:\/\/)?(?:www\.|m\.)?(?:youtube\.com\/(?:watch\?.*v=|shorts\/|embed\/|v\/)|youtu\.be\/)([a-zA-Z0-9_-]{11})'
    match = re.search(pattern, url)
    if match:
        return match.group(1)
        
    # 혹시 모를 다른 형태의 링크를 대비한 추가 검색
    fallback_match = re.search(r'(?:v=|\/)([a-zA-Z0-9_-]{11})', url)
    return fallback_match.group(1) if fallback_match else None

def get_youtube_transcript(video_id):
    try:
        # 자막 리스트 우선 확보 (자동생성 자막도 포함)
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        
        # 1. 한국어, 영어, 자동생성된 자막 순서대로 샅샅이 뒤져서 하나라도 찾아냄
        try:
            transcript = transcript_list.find_transcript(['ko', 'en', 'ko-KR', 'en-US'])
        except:
            # 2. 정 없으면 리스트에 잡히는 첫 번째 자막(다른 언어나 기본 자동생성)을 가져옴 (어차피 AI가 번역해줍니다!)
            transcript = list(transcript_list)[0]
            
        text = " ".join([t['text'] for t in transcript.fetch()])
        return text
    except Exception as e:
        error_type = type(e).__name__
        error_str = str(e)
        print(f"Transcript Error [{error_type}]: {error_str}")
        
        # 대표적인 에러 처리 안내 문구
        if error_type in ["TranscriptsDisabled", "NoTranscriptFound", "AttributeError"]:
            return "ERROR_DETAIL: 해당 영상에 열람 가능한 [CC 자막]이 없거나, 쇼츠(Shorts) 등 추출이 불가능한 구조의 영상입니다. (유튜버가 직접 입힌 자막은 가져올 수 없습니다.)"
        elif error_type == "VideoUnavailable":
            return "ERROR_DETAIL: 비공개되거나 삭제된 영상입니다."
        elif "Subtitles are" in error_str or "No transcripts" in error_str:
            return "ERROR_DETAIL: 영상에 [CC 자막]이 없거나 제공되지 않습니다."
        else:
            return f"ERROR_DETAIL: 자막 데이터 접근 실패 (특이 에러 발생: {error_type})"

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
    if not transcript or transcript.startswith("ERROR_DETAIL:"):
        error_msg = transcript.replace("ERROR_DETAIL: ", "") if transcript else "알 수 없는 에러가 발생했습니다."
        return render_template_string(HTML_TEMPLATE, url=url, error=f"이 영상에서 자막을 가져올 수 없습니다. 쇼츠나 자막(CC)이 꺼져있을 수 있습니다. 상세 이유: {error_msg}")
        
    result = analyze_recipe(transcript)
    if result["success"]:
        return render_template_string(HTML_TEMPLATE, url=url, recipe=result["recipe"])
    else:
        return render_template_string(HTML_TEMPLATE, url=url, error=f"AI 분석 실패: {result['error']}")

if __name__ == '__main__':
    app.run(debug=True)
