import json
import os
import re
from models.gemini_client import GeminiClient
from config import Config

class CodeRefactorer:
    """
    Handles code refactoring using Gemini with smart multi-file detection
    """
    def __init__(self):
        self.gemini = GeminiClient()
    
    def get_related_files(self, primary_file, related_filenames):
        """
        Load related files mentioned in smell detection
        """
        context = {}
        base_path = Config.LOCAL_REPO_PATH
        
        for fname in related_filenames[:3]:  # Limit to 3 files
            # Try to find the file
            for root, dirs, files in os.walk(base_path):
                if fname in files:
                    filepath = os.path.join(root, fname)
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            context[fname] = f.read()
                        print(f"Loaded related file: {fname}")
                    except (FileNotFoundError, PermissionError, UnicodeDecodeError) as e:
                        print(f"Could not load {fname}: {type(e).__name__}")
                    break
        
        return context
    
    def refactor(self, detection_result, use_model='gemini'):
        """
        Refactor code based on detected smells
        Returns either refactored code OR suggestions for multi-file refactorings
        """
        code = detection_result['code']
        result = detection_result['result']
        filename = detection_result['filename']
        
        if not result.get('has_smells'):
            return None
        
        smells_json = json.dumps(result['smells'], indent=2)
        
        # Get related files if mentioned
        related_files = result.get('related_files', [])
        context = self.get_related_files(detection_result['filepath'], related_files)
        
        print(f"\\nRefactoring {filename}...")
        refactored = self.gemini.refactor_code(code, smells_json, context)
        
        # Check if response is suggestions-only or actual refactored code
        is_suggestions = "=== REFACTORING SUGGESTIONS ===" in refactored
        
        if is_suggestions:
            # Extract suggestions
            suggestions = self._extract_suggestions(refactored)
            return {
                'original': code,
                'refactored_files': {},
                'suggestions': suggestions,
                'is_comment_only': True,
                'smells': result['smells'],
                'model_used': use_model
            }
        else:
            # Parse multi-file output
            files = self._parse_multifile_output(refactored)
            return {
                'original': code,
                'refactored_files': files,
                'suggestions': None,
                'is_comment_only': False,
                'smells': result['smells'],
                'model_used': use_model
            }
    
    def _extract_suggestions(self, text):
        """Extract refactoring suggestions from comment-only response"""
        # Remove the header marker
        text = text.replace("=== REFACTORING SUGGESTIONS ===", "")
        return text.strip()
    
    def _parse_multifile_output(self, refactored_text):
        """
        Parse output that might contain multiple files
        """
        # Remove the refactored code marker if present
        refactored_text = refactored_text.replace("=== REFACTORED CODE ===", "")
        
        # Check for file markers
        if '===' in refactored_text:
            files = {}
            parts = re.split(r'===\\s*(\\S+\\.java)\\s*===', refactored_text)
            
            for i in range(1, len(parts), 2):
                if i + 1 < len(parts):
                    fname = parts[i].strip()
                    code = parts[i + 1].strip()
                    files[fname] = self._clean_code(code)
            
            return files if files else {'main': self._clean_code(refactored_text)}
        
        return {'main': self._clean_code(refactored_text)}
    
    def _clean_code(self, code):
        """Remove markdown artifacts"""
        code = re.sub(r'```java\\s*', '', code)
        code = re.sub(r'```\\s*', '', code)
        return code.strip()
