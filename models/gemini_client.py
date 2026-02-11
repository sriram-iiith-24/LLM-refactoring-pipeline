from google import genai
from config import Config
from .rate_limiter import RateLimiter
import json
import re
import time

class GeminiClient:
    """
    Gemini client with automatic key rotation
    """
    def __init__(self):
        self.keys = [k for k in Config.GEMINI_KEYS if k]
        self.clients = []
        
        # Configure each key
        for key in self.keys:
            client = genai.Client(api_key=key)
            self.clients.append(client)
        
        self.rate_limiter = RateLimiter(
            rpm_limit=Config.GEMINI_RPM,
            num_keys=len(self.keys)
        )
        
        print(f"Initialized Gemini with {len(self.keys)} keys (Effective rate: {len(self.keys) * Config.GEMINI_RPM} RPM)")
    
    def extract_json(self, text):
        """
        Extract JSON from LLM response that might contain markdown or extra text
        """
        # Try to parse directly first
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        
        # Try to extract from markdown code blocks
        json_match = re.search(r'```(?:json)?\s*({.*?})\s*```', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        
        # Try to find JSON object in text
        json_match = re.search(r'{.*}', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass
        
        # Give up - return safe default
        print(f"WARNING: Could not extract JSON from response, using default")
        return {"has_smells": False, "smells": []}
    
    def generate(self, prompt, model_type='flash', temperature=0.1, json_mode=False):
        """
        Generate with automatic key rotation
        """
        key_idx = self.rate_limiter.wait_if_needed()
        
        # Map model type to actual model name
        model_map = {
            'flash': 'gemini-flash-lite-latest',
            'pro': 'gemini-flash-latest'
        }
        model_name = model_map.get(model_type, 'gemini-flash-lite-latest')
        
        # Timeout based on model type
        timeout = 300 if model_type == 'flash' else 600  # 2min for flash, 5min for pro
        
        # Retry loop for rate limits
        max_retries = 3
        for attempt in range(max_retries):
            print(f"Calling Gemini {model_type} (key {key_idx + 1})...", flush=True)
            
            try:
                client = self.clients[key_idx]
                
                config = {
                    'temperature': temperature
                }
                if json_mode:
                    config['response_mime_type'] = 'application/json'
                
                # Add timeout to prevent hanging
                import signal
                import platform
                
                response = None
                if platform.system() != 'Windows':
                    # Unix-like systems support signal timeout
                    def timeout_handler(signum, frame):
                        raise TimeoutError(f"Gemini API call timed out after {timeout} seconds")
                    
                    old_handler = signal.signal(signal.SIGALRM, timeout_handler)
                    signal.alarm(timeout)
                    
                    try:
                        response = client.models.generate_content(
                            model=model_name,
                            contents=prompt,
                            config=config
                        )
                    finally:
                        signal.alarm(0)  # Cancel alarm
                        signal.signal(signal.SIGALRM, old_handler)
                else:
                    # Windows - no timeout
                    response = client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                        config=config
                    )
                
                if not response or not response.text:
                    raise ValueError("Empty response from Gemini")
                
                print(f"Gemini {model_type}: Success ({len(response.text)} chars)")
                return response.text
            
            except TimeoutError as e:
                print(f"Gemini timeout: {e}")
                raise
            except Exception as e:
                error_str = str(e)
                # Check if it's a rate limit error (429)
                if '429' in error_str or 'RESOURCE_EXHAUSTED' in error_str:
                    # Extract retry delay from error if available
                    wait_time = 30 * (attempt + 1)  # Exponential backoff: 30s, 60s, 90s
                    if 'retryDelay' in error_str:
                        import re
                        match = re.search(r'retryDelay["\s:]+(\d+)', error_str)
                        if match:
                            wait_time = int(match.group(1)) + 5  # Add 5 seconds buffer
                    
                    if attempt < max_retries - 1:
                        print(f"Rate limited. Waiting {wait_time}s before retry {attempt + 2}/{max_retries}...", flush=True)
                        time.sleep(wait_time)
                        # Try next key on retry
                        key_idx = (key_idx + 1) % len(self.clients)
                        continue
                
                print(f"Gemini error: {type(e).__name__}: {e}")
                raise
        
        raise Exception(f"Failed after {max_retries} retries due to rate limits")
    
    def detect_smells(self, code, filename):
        """Detect design smells using Flash (faster)"""
        line_count = len(code.splitlines())
        
        prompt = f"""You are a strict senior Java code reviewer specializing in detecting design smells.

Analyze this Java file ({line_count} lines) for the following design smells. Be THOROUGH and evaluate ALL smells:

**1. God Class (Single Responsibility Violation)**
   - Class has multiple unrelated responsibilities
   - More than 5 distinct responsibilities (examine method groupings by purpose)
   - Too many instance variables (>10)
   - File size >400 lines often indicates this
   
**2. Feature Envy**
   - A method that uses more methods/fields from another class than its own
   - Method accessing external class data extensively
   - Suggests method belongs in the other class
   
**3. Data Clumps**
   - Same group of 3+ parameters appearing together across multiple methods
   - Same fields repeatedly accessed together
   - Suggests missing object abstraction
   
**4. Shotgun Surgery**
   - Single logical change requires modifications across multiple methods or classes
   - Related behavior scattered across the codebase
   - Indicates poor cohesion
   
**5. Long Method**
   - Methods over 30 lines (especially >50 lines)
   - Complex logic that should be decomposed
   - Multiple levels of nesting (>3)

Examine the code carefully for EACH smell type. Return findings for ALL detected smells, not just one.

Return format:
{{
  "has_smells": true,
  "smells": [
    {{
      "type": "God Class",
      "severity": "high",
      "line_range": "1-{line_count}",
      "evidence": "Describe specific evidence - method groupings, responsibilities",
      "affected_methods": ["method1", "method2", "method3"]
    }}
  ],
  "related_files": []
}}

If somehow there are truly no smells (unlikely for a {line_count}-line file):
{{"has_smells": false, "smells": []}}

File: {filename} ({line_count} lines)

{code}
"""
        response = self.generate(prompt, model_type='flash', json_mode=True)
        
        # Extract JSON even if response includes extra text
        try:
            result = self.extract_json(response)
            return json.dumps(result)
        except Exception as e:
            print(f"WARNING: JSON extraction failed: {e}")
            return json.dumps({"has_smells": False, "smells": []})
    
    def refactor_code(self, code, smells_json, context_files=None):
        """Refactor using Pro with multi-file impact detection"""
        context = ""
        if context_files:
            context = "\n\nRELATED FILES FOR CONTEXT:\n"
            for fname, content in context_files.items():
                context += f"\n--- {fname} ---\n{content[:10000]}\n"
        
        prompt = f"""
You are an expert Java refactoring engineer.

DETECTED SMELLS:
{smells_json}

IMPORTANT INSTRUCTIONS:
1. FIRST, analyze if refactoring these smells would require changes to OTHER files:
   - Would extracting classes require updating imports in other files?
   - Would changing method signatures break calling code?
   - Would moving methods affect other classes that depend on them?

2. If refactoring requires MULTI-FILE CHANGES:
   - DO NOT modify the code
   - Instead, return ONLY comments starting with "// REFACTORING SUGGESTION:"
   - Explain what changes are needed and why
   - List which files would be affected
   - Provide step-by-step refactoring guide

3. If refactoring can be done WITHIN THIS FILE ONLY:
   - Proceed with the refactoring
   - Preserve all public method signatures (no breaking changes)
   - Add JavaDoc comments explaining major changes
   - Follow Java naming conventions
   - Extract new private methods or inner classes as needed
   - Return complete, compilable code

RULES:
- Public API must remain unchanged
- No changes that affect external callers
- If uncertain, provide comments instead of code
- Be conservative - suggest comments for complex cases

{context}

ORIGINAL CODE TO ANALYZE AND REFACTOR:
{code}

RETURN FORMAT:
If you're providing refactored code:
=== REFACTORED CODE ===
[Complete refactored code]

If you're providing suggestions only:
=== REFACTORING SUGGESTIONS ===
[Comments and guidance only - do NOT include actual code changes]
"""
        return self.generate(prompt, model_type='pro', temperature=0.3)
