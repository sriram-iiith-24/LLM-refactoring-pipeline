import logging
import os
from datetime import datetime

class Logger:
    """
    Logging utility for the refactoring pipeline
    """
    
    @staticmethod
    def setup(name='refactoring_pipeline', log_file=None, level=logging.INFO):
        """
        Setup logger with console and file handlers
        
        Args:
            name: Logger name
            log_file: Optional log file path (defaults to logs/pipeline_YYYYMMDD.log)
            level: Logging level
        
        Returns:
            Logger instance
        """
        logger = logging.getLogger(name)
        logger.setLevel(level)
        
        # Avoid duplicate handlers
        if logger.handlers:
            return logger
        
        # Format
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        
        # File handler
        if log_file is None:
            os.makedirs('logs', exist_ok=True)
            log_file = f"logs/pipeline_{datetime.now().strftime('%Y%m%d')}.log"
        
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
        return logger
    
    @staticmethod
    def log_smell_detection(logger, filename, smells):
        """Log smell detection results"""
        logger.info(f"Analyzed {filename}")
        if smells:
            logger.warning(f"Found {len(smells)} smell(s) in {filename}")
            for smell in smells:
                logger.warning(f"  - {smell['type']}: {smell['evidence']}")
        else:
            logger.info(f"No smells detected in {filename}")
    
    @staticmethod
    def log_refactoring(logger, filename, model, success=True):
        """Log refactoring results"""
        if success:
            logger.info(f"Successfully refactored {filename} using {model}")
        else:
            logger.error(f"Failed to refactor {filename} using {model}")
    
    @staticmethod
    def log_pr_creation(logger, pr_url):
        """Log PR creation"""
        logger.info(f"Created PR: {pr_url}")
