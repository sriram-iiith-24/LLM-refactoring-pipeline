import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # API Keys
    GEMINI_KEYS = [
        os.getenv('GEMINI_KEY_1'),
        os.getenv('GEMINI_KEY_2')
    ]
    DEEPSEEK_KEY = os.getenv('DEEPSEEK_KEY')
    DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
    
    # GitHub
    GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
    GITHUB_REPO = os.getenv('GITHUB_REPO')
    
    # Local paths
    LOCAL_REPO_PATH = os.getenv('LOCAL_REPO_PATH')
    OUTPUT_DIR = 'refactoring_reports'
    
    # Rate limits
    GEMINI_RPM = 15
    DEEPSEEK_RPM = 60
    
    # ============================================
    # FILE DISCOVERY SETTINGS
    # ============================================
    
    # Scanning mode: 'all', 'changed', 'large', 'package', 'manual'
    SCAN_MODE = os.getenv('SCAN_MODE', 'large')
    
    # For 'changed' mode: scan files changed in last N hours
    SCAN_CHANGED_HOURS = int(os.getenv('SCAN_CHANGED_HOURS', 24))
    
    # For 'large' mode: minimum lines to be considered
    # Targets files that are large enough to exhibit design smells
    # 200-400 lines: Common range for various design smells
    SCAN_MIN_LINES = int(os.getenv('SCAN_MIN_LINES', 200))
    
    # For 'package' mode: package pattern to match
    SCAN_PACKAGE = os.getenv('SCAN_PACKAGE', 'org/apache/roller/business')
    
    # For 'manual' mode: specific files (comma-separated in .env)
    MANUAL_FILES = os.getenv('MANUAL_FILES', '').split(',') if os.getenv('MANUAL_FILES') else []
    
    # Maximum files to process per run (to avoid hitting rate limits)
    MAX_FILES_PER_RUN = int(os.getenv('MAX_FILES_PER_RUN', 10))
    
    # Directories to exclude from scanning
    EXCLUDE_DIRS = ['target', 'build', 'test', 'generated', '.git', 'node_modules']
    
    # ============================================
    
    # ============================================
    # STATE MANAGEMENT
    # ============================================
    
    # State file location
    STATE_FILE = 'refactoring_reports/pipeline_state.json'
    
    # Maximum retry attempts for failed files
    MAX_RETRIES = int(os.getenv('MAX_RETRIES', 3))
    
    # Enable/disable state management
    ENABLE_STATE_MANAGEMENT = os.getenv('ENABLE_STATE_MANAGEMENT', 'true').lower() == 'true'
    
    # ============================================
    
    @classmethod
    def validate(cls):
        missing = []
        if not any(cls.GEMINI_KEYS):
            missing.append('GEMINI_KEY_1 or GEMINI_KEY_2')
        if not cls.GITHUB_TOKEN:
            missing.append('GITHUB_TOKEN')
        if not cls.LOCAL_REPO_PATH:
            missing.append('LOCAL_REPO_PATH')
        
        if missing:
            raise ValueError(f"Missing required env vars: {', '.join(missing)}")
