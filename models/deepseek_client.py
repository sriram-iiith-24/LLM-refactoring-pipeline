import requests
import json
import re
from config import Config
from .rate_limiter import RateLimiter

class DeepSeekClient:
    """
    DeepSeek API client (code-specialized)
    """
    def __init__(self):
        self.api_url = Config.DEEPSEEK_API_URL
        self.api_key = Config.DEEPSEEK_KEY
        self.rate_limiter = RateLimiter(rpm_limit=Config.DEEPSEEK_RPM, num_keys=1)
        
        print(f"✅ Initialized DeepSeek (60 RPM)")
    
    def generate(self, prompt, temperature=0.3):
        """Call DeepSeek API"""
        self.rate_limiter.wait_if_needed()
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": "You are an expert Java code reviewer and refactoring engineer. Always respond with valid JSON when asked for JSON."},
                {"role": "user", "content": prompt}
            ],
            "temperature": temperature
        }
        
        try:
            print(f"🔄 Calling DeepSeek...", flush=True)
            response = requests.post(self.api_url, headers=headers, json=payload, timeout=120)
            response.raise_for_status()
            
            result = response.json()['choices'][0]['message']['content']
            print(f"✓ DeepSeek: Success ({len(result)} chars)")
            return result
        
        except Exception as e:
            print(f"✗ DeepSeek error: {e}")
            raise
    
    def extract_json(self, text):
        """Extract JSON from text that might have markdown or extra content"""
        # Try direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        
        # Try extracting from markdown code block
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        
        # Try to find JSON object in text
        json_match = re.search(r'\{[\s\S]*\}', text)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass
        
        return {"has_smells": False, "smells": []}
    
    def detect_smells(self, code, filename):
        """Detect design smells using DeepSeek (fallback for Gemini)"""
        line_count = len(code.splitlines())
        
        prompt = f"""Analyze this Java file for design smells. The file has {line_count} lines.

Look for these smells:
1. God Class (>400 lines, too many responsibilities)
2. Long Method (>30 lines)
3. Feature Envy
4. Data Clumps

Return ONLY valid JSON in this format:
{{
  "has_smells": true,
  "smells": [
    {{
      "type": "God Class",
      "severity": "high",
      "line_range": "1-{line_count}",
      "evidence": "description",
      "affected_methods": ["method1", "method2"]
    }}
  ]
}}

If no smells: {{"has_smells": false, "smells": []}}

File: {filename} ({line_count} lines)

{code}
"""
        response = self.generate(prompt)
        result = self.extract_json(response)
        return json.dumps(result)
    
    def refactor_code(self, code, smells_json):
        """Refactor using DeepSeek"""
        prompt = f"""
Refactor this Java code to fix these design smells:

SMELLS:
{smells_json}

RULES:
- Preserve public interfaces
- Add comments explaining changes
- Return complete code only

CODE:
{code}
"""
        return self.generate(prompt)

