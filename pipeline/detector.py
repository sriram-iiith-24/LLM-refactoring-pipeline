import json
import os
from models.gemini_client import GeminiClient
from models.deepseek_client import DeepSeekClient

class SmellDetector:
    """
    Orchestrates smell detection using Gemini with DeepSeek fallback
    """
    def __init__(self):
        self.gemini = GeminiClient()
        self.deepseek = None  # Lazy init
    
    def _get_deepseek(self):
        """Lazy initialize DeepSeek client"""
        if self.deepseek is None:
            self.deepseek = DeepSeekClient()
        return self.deepseek
    
    def analyze_file(self, filepath):
        """
        Analyze a single Java file
        Returns: dict with smells and related files
        """
        filename = os.path.basename(filepath)
        
        print(f"\n🔍 Analyzing {filename}...")
        
        with open(filepath, 'r', encoding='utf-8') as f:
            code = f.read()
        
        # Try Gemini first, fall back to DeepSeek
        result_json = None
        try:
            result_json = self.gemini.detect_smells(code, filename)
        except Exception as gemini_error:
            error_str = str(gemini_error)
            if '429' in error_str or 'RESOURCE_EXHAUSTED' in error_str:
                print(f"   ⚠️  Gemini quota exhausted, using DeepSeek fallback...")
                try:
                    deepseek = self._get_deepseek()
                    result_json = deepseek.detect_smells(code, filename)
                except Exception as ds_error:
                    print(f"   ❌ DeepSeek also failed: {ds_error}")
                    raise
            else:
                raise
        
        try:
            result = json.loads(result_json)
        except json.JSONDecodeError as e:
            print(f"   ⚠️  Failed to parse JSON response: {e}")
            print(f"   Response preview: {result_json[:200]}...")
            # Return safe default
            result = {"has_smells": False, "smells": []}
        
        if result.get('has_smells'):
            smells = result['smells']
            print(f"   ⚠️  Found {len(smells)} smell(s):")
            for smell in smells:
                print(f"      - {smell.get('type', 'Unknown')} ({smell.get('severity', 'unknown')})")
        else:
            print(f"   ✨ No major smells detected")
        
        return {
            'filepath': filepath,
            'filename': filename,
            'code': code,
            'result': result
        }
