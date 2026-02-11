import os
import subprocess
from config import Config

class FileScanner:
    """
    Discovers Java files to scan based on configured strategy
    """
    
    def __init__(self):
        self.repo_path = Config.LOCAL_REPO_PATH
        self.mode = Config.SCAN_MODE
        
        if not self.repo_path:
            raise ValueError("LOCAL_REPO_PATH is not configured in .env")
    
    def discover_files(self):
        """
        Main entry point - discovers files based on SCAN_MODE
        """
        print(f"\n📂 File Discovery Mode: {self.mode.upper()}")
        
        if self.mode == 'all':
            files = self._scan_all()
        elif self.mode == 'changed':
            files = self._scan_changed()
        elif self.mode == 'large':
            files = self._scan_large()
        elif self.mode == 'package':
            files = self._scan_package()
        elif self.mode == 'manual':
            files = self._scan_manual()
        else:
            raise ValueError(f"Unknown scan mode: {self.mode}")
        
        # Apply max files limit
        if len(files) > Config.MAX_FILES_PER_RUN:
            print(f"⚠️  Found {len(files)} files, limiting to {Config.MAX_FILES_PER_RUN}")
            files = files[:Config.MAX_FILES_PER_RUN]
        
        print(f"✅ Selected {len(files)} files for analysis")
        return files
    
    def _scan_all(self):
        """Scan all Java files"""
        print("   Scanning entire repository...")
        return self._get_all_java_files()
    
    def _scan_changed(self):
        """Scan recently changed files"""
        hours = Config.SCAN_CHANGED_HOURS
        print(f"   Scanning files changed in last {hours} hours...")
        
        try:
            os.chdir(self.repo_path)
            
            # Get changed files from git
            result = subprocess.run(
                ['git', 'diff', '--name-only', f'HEAD@{{{hours} hours ago}}..HEAD'],
                capture_output=True,
                text=True,
                check=True
            )
            
            changed_files = result.stdout.strip().split('\n')
            java_files = [
                os.path.join(self.repo_path, f) 
                for f in changed_files 
                if f.endswith('.java') and os.path.exists(os.path.join(self.repo_path, f))
            ]
            
            if not java_files:
                print("   ⚠️  No changed Java files found, falling back to 'large' mode")
                return self._scan_large()
            
            return java_files
        
        except Exception as e:
            print(f"   ⚠️  Git error: {e}, falling back to 'large' mode")
            return self._scan_large()
    
    def _scan_large(self):
        """Scan files above minimum line count"""
        min_lines = Config.SCAN_MIN_LINES
        print(f"   Scanning files with ≥{min_lines} lines...")
        
        all_files = self._get_all_java_files()
        large_files = []
        
        for filepath in all_files:
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    line_count = sum(1 for _ in f)
                
                if line_count >= min_lines:
                    large_files.append((filepath, line_count))
            except:
                pass
        
        # Sort by size (largest first - most likely to have God Class)
        large_files.sort(key=lambda x: x[1], reverse=True)
        
        for filepath, lines in large_files[:10]:
            print(f"      - {os.path.basename(filepath)}: {lines} lines")
        
        return [f[0] for f in large_files]
    
    def _scan_package(self):
        """Scan specific package"""
        package = Config.SCAN_PACKAGE
        print(f"   Scanning package: {package}")
        
        all_files = self._get_all_java_files()
        package_files = [f for f in all_files if package in f]
        
        return package_files
    
    def _scan_manual(self):
        """Use manually specified files"""
        print("   Using manually specified files...")
        
        files = []
        for rel_path in Config.MANUAL_FILES:
            if not rel_path.strip():
                continue
            
            full_path = os.path.join(self.repo_path, rel_path.strip())
            if os.path.exists(full_path):
                files.append(full_path)
                print(f"      ✓ {rel_path}")
            else:
                print(f"      ✗ Not found: {rel_path}")
        
        return files
    
    def _get_all_java_files(self):
        """
        Recursively find all .java files
        """
        java_files = []
        
        for root, dirs, files in os.walk(self.repo_path):
            # Exclude certain directories
            dirs[:] = [d for d in dirs if d not in Config.EXCLUDE_DIRS]
            
            for file in files:
                if file.endswith('.java'):
                    full_path = os.path.join(root, file)
                    java_files.append(full_path)
        
        return java_files
