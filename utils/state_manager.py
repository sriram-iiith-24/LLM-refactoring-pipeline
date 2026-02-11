#!/usr/bin/env python3
"""
Robust State Manager for Refactoring Pipeline

Handles:
- Progress tracking across interruptions
- Partial completion (detection done, refactoring pending)
- Retry logic with configurable max attempts
- Statistics and cost tracking
- Atomic saves to prevent corruption
- File hash tracking to detect changes
"""

import json
import os
import hashlib
import time
from datetime import datetime
from threading import RLock
from pathlib import Path
from typing import Dict, List, Optional, Tuple

class StateManager:
    """
    Thread-safe state manager for pipeline progress tracking
    """
    
    def __init__(self, state_file='refactoring_reports/pipeline_state.json', max_retries=3):
        self.state_file = state_file
        self.max_retries = max_retries
        # Use RLock (re-entrant lock) instead of Lock to allow nested locking
        # This fixes deadlock when methods that hold the lock call _save_state()
        self.lock = RLock()
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(state_file), exist_ok=True)
        
        # Load or initialize state
        self.state = self._load_state()
        
        # Track current run
        self._current_run_id = self._init_current_run()
    
    def _load_state(self) -> Dict:
        """Load state from disk, with backup recovery"""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r') as f:
                    state = json.load(f)
                
                # Validate structure
                if 'version' in state and 'files' in state:
                    return state
                else:
                    print("WARNING: State file has old format, resetting...")
                    return self._create_new_state()
            
            except json.JSONDecodeError as e:
                print(f"WARNING: Corrupted state file: {e}")
                
                # Try backup
                backup = f"{self.state_file}.backup"
                if os.path.exists(backup):
                    print("   Attempting restore from backup...")
                    try:
                        with open(backup, 'r') as f:
                            return json.load(f)
                    except:
                        pass
                
                # Reset if backup fails
                print("   Creating new state...")
                return self._create_new_state()
        
        return self._create_new_state()
    
    def _create_new_state(self) -> Dict:
        """Create fresh state structure with enhanced metrics"""
        return {
            'version': '1.1',  # Bumped version for enhanced stats
            'created_at': datetime.now().isoformat(),
            'last_updated': datetime.now().isoformat(),
            'runs': [],
            'files': {},
            'statistics': {
                'total_files_processed': 0,
                'completed': 0,
                'failed': 0,
                'skipped': 0,
                'prs_created': 0,
                'comment_only_refactorings': 0,  # NEW
                'code_refactorings': 0,  # NEW
                'api_calls': {
                    'gemini_flash': 0,
                    'gemini_pro': 0
                },
                'estimated_cost': 0.0,
                'total_processing_time_seconds': 0,
                'smell_breakdown': {}  # NEW: track which smells are most common
            }
        }
    
    def _init_current_run(self) -> int:
        """Initialize or resume current run"""
        runs = self.state.get('runs', [])
        
        # Check if there's an incomplete run
        if runs and 'completed_at' not in runs[-1]:
            # Resume incomplete run
            run_id = runs[-1]['run_id']
            print(f"Resuming run #{run_id}")
            return run_id
        else:
            # Start new run
            run_id = len(runs) + 1
            runs.append({
                'run_id': run_id,
                'started_at': datetime.now().isoformat(),
                'files_processed': 0,
                'prs_created': 0
            })
            self.state['runs'] = runs
            self._save_state()
            print(f"Starting run #{run_id}")
            return run_id
    
    def _save_state(self):
        """Atomically save state to disk"""
        with self.lock:
            try:
                # Update timestamp
                self.state['last_updated'] = datetime.now().isoformat()
                
                # Atomic write: temp file → rename
                temp_file = f"{self.state_file}.tmp"
                with open(temp_file, 'w') as f:
                    json.dump(self.state, f, indent=2)
                
                # Backup existing state
                if os.path.exists(self.state_file):
                    backup = f"{self.state_file}.backup"
                    os.replace(self.state_file, backup)
                
                # Rename temp to actual
                os.replace(temp_file, self.state_file)
            
            except Exception as e:
                print(f"WARNING: Failed to save state: {e}")
    
    def _get_file_hash(self, filepath: str) -> str:
        """Get SHA256 hash of file to detect changes"""
        try:
            with open(filepath, 'rb') as f:
                return hashlib.sha256(f.read()).hexdigest()[:16]
        except:
            return ''
    
    def _get_file_state(self, filepath: str) -> Dict:
        """Get or create file state with enhanced tracking"""
        if filepath not in self.state['files']:
            self.state['files'][filepath] = {
                'status': 'pending',
                'file_hash': self._get_file_hash(filepath),
                'detection': {'completed': False},
                'refactoring': {
                    'gemini': {
                        'completed': False,
                        'is_comment_only': False  # NEW
                    }
                },
                'attempts': 0,
                'created_at': datetime.now().isoformat()
            }
        
        return self.state['files'][filepath]
    
    # Public API
    
    def should_process(self, filepath: str) -> Tuple[bool, str]:
        """
        Check if file should be processed
        
        Returns:
            (should_process, reason)
        """
        with self.lock:
            file_state = self._get_file_state(filepath)
            
            # Check if file exists
            if not os.path.exists(filepath):
                return False, 'file_not_found'
            
            # Check if completed
            if file_state['status'] == 'completed':
                # Check if file changed
                current_hash = self._get_file_hash(filepath)
                if current_hash != file_state.get('file_hash', ''):
                    print(f"WARNING: File changed since last run, re-processing...")
                    file_state['status'] = 'pending'
                    file_state['file_hash'] = current_hash
                    return True, 'file_changed'
                
                return False, 'already_completed'
            
            # Check if permanently failed
            if file_state['status'] == 'failed' and file_state['attempts'] >= self.max_retries:
                return False, 'max_retries_exceeded'
            
            # Should process
            return True, 'ready'
    
    def start_processing(self, filepath: str) -> Dict:
        """Mark file as started, return file state"""
        with self.lock:
            file_state = self._get_file_state(filepath)
            file_state['attempts'] += 1
            file_state['status'] = 'processing'
            file_state['last_attempt'] = datetime.now().isoformat()
            file_state['start_time'] = time.time()
            
            self._save_state()
            return file_state
    
    def track_smell_stats(self, smells):
        """Track which smells are detected most frequently"""
        with self.lock:
            breakdown = self.state['statistics'].get('smell_breakdown', {})
            
            for smell in smells:
                smell_type = smell['type']
                if smell_type not in breakdown:
                    breakdown[smell_type] = {
                        'count': 0,
                        'severity_breakdown': {'low': 0, 'medium': 0, 'high': 0}
                    }
                breakdown[smell_type]['count'] += 1
                severity = smell.get('severity', 'medium')
                breakdown[smell_type]['severity_breakdown'][severity] += 1
            
            self.state['statistics']['smell_breakdown'] = breakdown
            self._save_state()
    def mark_detection_complete(self, filepath: str, has_smells: bool):
        """Mark smell detection phase as complete"""
        with self.lock:
            file_state = self._get_file_state(filepath)
            file_state['detection'] = {
                'completed': True,
                'timestamp': datetime.now().isoformat(),
                'has_smells': has_smells
            }
            
            # Track API call
            self.state['statistics']['api_calls']['gemini_flash'] += 1
            
            self._save_state()
    
    def mark_refactoring_complete(self, filepath: str, model: str, pr_number: Optional[int] = None, pr_url: Optional[str] = None, is_comment_only: bool = False):
        """Mark refactoring for specific model as complete"""
        with self.lock:
            file_state = self._get_file_state(filepath)
            
            file_state['refactoring'][model] = {
                'completed': True,
                'timestamp': datetime.now().isoformat(),
                'is_comment_only': is_comment_only  # NEW
            }
            
            if pr_number:
                file_state['refactoring'][model]['pr_number'] = pr_number
                file_state['refactoring'][model]['pr_url'] = pr_url
            
            # Track API call
            if model == 'gemini':
                self.state['statistics']['api_calls']['gemini_pro'] += 1
            
            self._save_state()
    
    def mark_completed(self, filepath: str):
        """Mark file as fully completed with enhanced tracking"""
        with self.lock:
            file_state = self._get_file_state(filepath)
            file_state['status'] = 'completed'
            file_state['completed_at'] = datetime.now().isoformat()
            
            # Calculate processing time
            if 'start_time' in file_state:
                duration = time.time() - file_state['start_time']
                file_state['processing_time_seconds'] = int(duration)
                self.state['statistics']['total_processing_time_seconds'] += int(duration)
                del file_state['start_time']
            
            # Update statistics
            self.state['statistics']['completed'] += 1
            self.state['statistics']['total_files_processed'] += 1
            
            # Track refactoring type (NEW)
            is_comment_only = file_state['refactoring']['gemini'].get('is_comment_only', False)
            if is_comment_only:
                self.state['statistics']['comment_only_refactorings'] += 1
            else:
                self.state['statistics']['code_refactorings'] += 1
            
            # Count PRs from gemini
            prs = 0
            if file_state['refactoring']['gemini'].get('pr_number'):
                prs = 1
            self.state['statistics']['prs_created'] += prs
            
            # Update current run
            runs = self.state['runs']
            if runs:
                runs[-1]['files_processed'] += 1
                runs[-1]['prs_created'] += prs
            
            self._save_state()
            print(f"Saved progress: {os.path.basename(filepath)}")
    
    def mark_failed(self, filepath: str, error: str, phase: str = 'unknown'):
        """Mark file as failed"""
        with self.lock:
            file_state = self._get_file_state(filepath)
            file_state['last_error'] = str(error)
            file_state['failed_phase'] = phase
            file_state['last_failed'] = datetime.now().isoformat()
            
            # Check if should give up
            if file_state['attempts'] >= self.max_retries:
                file_state['status'] = 'failed'
                self.state['statistics']['failed'] += 1
                print(f"Marked as failed: {os.path.basename(filepath)} (max retries exceeded)")
            else:
                file_state['status'] = 'pending'  # Will retry
                print(f"Failed (attempt {file_state['attempts']}/{self.max_retries}): {os.path.basename(filepath)}")
            
            # Clean up timing
            if 'start_time' in file_state:
                del file_state['start_time']
            
            self._save_state()
    
    def mark_skipped(self, filepath: str, reason: str):
        """Mark file as skipped"""
        with self.lock:
            file_state = self._get_file_state(filepath)
            file_state['status'] = 'skipped'
            file_state['skip_reason'] = reason
            file_state['skipped_at'] = datetime.now().isoformat()
            
            self.state['statistics']['skipped'] += 1
            self._save_state()
    
    def complete_run(self):
        """Mark current run as complete"""
        with self.lock:
            runs = self.state['runs']
            if runs and 'completed_at' not in runs[-1]:
                runs[-1]['completed_at'] = datetime.now().isoformat()
                self._save_state()
    
    def get_summary(self) -> Dict:
        """Get current state summary"""
        with self.lock:
            stats = self.state['statistics']
            
            # Files that can be retried
            pending = sum(
                1 for f in self.state['files'].values()
                if f['status'] in ['pending', 'processing'] and f['attempts'] < self.max_retries
            )
            
            return {
                'total_discovered': len(self.state['files']),
                'completed': stats['completed'],
                'failed': stats['failed'],
                'skipped': stats['skipped'],
                'pending': pending,
                'prs_created': stats['prs_created'],
                'api_calls': stats['api_calls'],
                'processing_time': stats['total_processing_time_seconds']
            }
    
    def print_summary(self):
        """Print formatted summary"""
        summary = self.get_summary()
        
        print("\n" + "="*70)
        print("PIPELINE STATE SUMMARY")
        print("="*70)
        print(f"Total files discovered:  {summary['total_discovered']}")
        print(f"Completed:             {summary['completed']}")
        print(f"Failed (max retries):  {summary['failed']}")
        print(f"Skipped:               {summary['skipped']}")
        print(f"Pending/Retry:         {summary['pending']}")
        print(f"PRs created:           {summary['prs_created']}")
        print(f"\nAPI Calls:")
        for model, count in summary['api_calls'].items():
            print(f"   {model}: {count}")
        
        if summary['processing_time'] > 0:
            minutes = summary['processing_time'] // 60
            seconds = summary['processing_time'] % 60
            print(f"\nTotal processing time: {minutes}m {seconds}s")
        
        print("="*70)
    
    def reset(self):
        """Clear all state (use with caution!)"""
        with self.lock:
            self.state = self._create_new_state()
            self._save_state()
            print("State reset complete")
    
    def get_failed_files(self) -> List[Dict]:
        """Get list of permanently failed files"""
        with self.lock:
            failed = []
            for filepath, state in self.state['files'].items():
                if state['status'] == 'failed':
                    failed.append({
                        'file': filepath,
                        'attempts': state['attempts'],
                        'error': state.get('last_error', 'Unknown'),
                        'phase': state.get('failed_phase', 'unknown')
                    })
            return failed
    
    def has_previous_run(self) -> bool:
        """Check if there's previous state to resume from"""
        return len(self.state.get('files', {})) > 0
