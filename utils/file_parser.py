import os
import re

class FileParser:
    """
    Utility for parsing Java files and extracting metadata
    """
    
    @staticmethod
    def extract_class_name(code):
        """Extract the main class name from Java code"""
        match = re.search(r'public\s+class\s+(\w+)', code)
        return match.group(1) if match else None
    
    @staticmethod
    def extract_package_name(code):
        """Extract package declaration from Java code"""
        match = re.search(r'package\s+([\w.]+);', code)
        return match.group(1) if match else None
    
    @staticmethod
    def extract_imports(code):
        """Extract all import statements"""
        imports = re.findall(r'import\s+([\w.]+);', code)
        return imports
    
    @staticmethod
    def extract_methods(code):
        """Extract method signatures"""
        # Simple regex for method extraction (not perfect but functional)
        pattern = r'(public|private|protected)\s+(?:static\s+)?(\w+)\s+(\w+)\s*\([^)]*\)'
        methods = re.findall(pattern, code)
        return [{'visibility': m[0], 'return_type': m[1], 'name': m[2]} for m in methods]
    
    @staticmethod
    def count_lines(code):
        """Count lines of code (excluding blank lines and comments)"""
        lines = code.split('\n')
        code_lines = 0
        in_block_comment = False
        
        for line in lines:
            stripped = line.strip()
            
            # Handle block comments
            if '/*' in stripped:
                in_block_comment = True
            if '*/' in stripped:
                in_block_comment = False
                continue
            
            # Skip blank lines, single-line comments, and block comments
            if not stripped or stripped.startswith('//') or in_block_comment:
                continue
            
            code_lines += 1
        
        return code_lines
    
    @staticmethod
    def find_java_files(directory, exclude_patterns=None):
        """
        Recursively find all Java files in a directory
        
        Args:
            directory: Root directory to search
            exclude_patterns: List of patterns to exclude (e.g., ['test/', 'generated/'])
        
        Returns:
            List of absolute file paths
        """
        exclude_patterns = exclude_patterns or []
        java_files = []
        
        for root, dirs, files in os.walk(directory):
            # Skip excluded directories
            if any(pattern in root for pattern in exclude_patterns):
                continue
            
            for file in files:
                if file.endswith('.java'):
                    java_files.append(os.path.join(root, file))
        
        return java_files
