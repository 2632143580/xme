"""快速验证：火山引擎 API Key + 模型 ID 是否正确。"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

import openai

api_key = os.getenv("VOLCENGINE_API_KEY", "")
base_url = os.getenv("VOLCENGINE_BASE_URL", "")
model = os.getenv("VOLCENGINE_MODEL", "")

print(f"API Key: {api_key[:8]}...{api_key[-4:]}")
print(f"Base URL: {base_url}")
print(f"Model: {model}")
print()

client = openai.OpenAI(api_key=api_key, base_url=base_url)

try:
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "你好，请只回复'OK'两个字母"}],
        max_tokens=10,
        timeout=15,
    )
    content = resp.choices[0].message.content
    print(f"✅ API 调用成功！模型回复: {content}")
    print(f"Usage: {resp.usage}")
except Exception as e:
    print(f"❌ API 调用失败: {e}")
    sys.exit(1)
