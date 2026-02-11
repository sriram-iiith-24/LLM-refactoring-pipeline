#!/usr/bin/env python3
"""
Automated Refactoring Pipeline with Dynamic File Discovery
"""

import os
import json
import sys
import signal
import argparse
from config import Config
from utils.file_scanner import FileScanner
from utils.state_manager import StateManager
from pipeline.detector import SmellDetector
from pipeline.refactorer import CodeRefactorer
from pipeline.git_handler import GitHubHandler
from pipeline.feedback_loop import FeedbackLoop

def save_report(detection, refactoring, output_dir):
    """Save refactoring report with comment-only support"""
    os.makedirs(output_dir, exist_ok=True)
    
    filename = detection['filename'].replace('.java', '')
    
    # Save original
    with open(f"{output_dir}/{filename}_original.java", 'w') as f:
        f.write(detection['code'])
    
    # Check if comment-only mode
    is_comment_only = refactoring.get('is_comment_only', False)
    
    if is_comment_only:
        # Save suggestions file
        with open(f"{output_dir}/{filename}_refactoring_suggestions.md", 'w') as f:
            f.write(f"# Refactoring Suggestions for {detection['filename']}\n\n")
            f.write("**Multi-file changes required - manual refactoring recommended**\n\n")
            f.write("## Detected Smells\n\n")
            for smell in refactoring.get('smells', []):
                f.write(f"- **{smell['type']}** ({smell['severity']})\n")
            f.write("\n## Refactoring Guidance\n\n")
            f.write(refactoring.get('suggestions', ''))
        print(f"Multi-file refactoring - saved suggestions to {output_dir}/{filename}_refactoring_suggestions.md")
    else:
        # Save refactored code (existing logic)
        for fname, code in refactoring.get('refactored_files', {}).items():
            output_name = f"{filename}_refactored.java" if fname == 'main' else fname
            with open(f"{output_dir}/{output_name}", 'w') as f:
                f.write(code)
        print(f"Refactored code saved to {output_dir}/")
    
    # Save metadata
    metadata = {
        'filename': detection['filename'],
        'filepath': detection['filepath'],
        'smells_detected': refactoring.get('smells', []),
        'model_used': refactoring.get('model_used', 'gemini'),
        'is_comment_only': is_comment_only,
        'files_created': list(refactoring.get('refactored_files', {}).keys())
    }
    
    with open(f"{output_dir}/{filename}_metadata.json", 'w') as f:
        json.dump(metadata, f, indent=2)
    
    return is_comment_only

def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Automated Refactoring Pipeline')
    parser.add_argument('--reset', action='store_true', help='Reset state and start fresh')
    parser.add_argument('--stats', action='store_true', help='Show statistics and exit')
    parser.add_argument('--failed', action='store_true', help='Show failed files and exit')
    parser.add_argument('--monitor', action='store_true', help='Enable PR feedback monitoring')
    parser.add_argument('--monitor-interval', type=int, default=3600, help='Feedback check interval in seconds (default: 3600)')
    return parser.parse_args()

# Global state manager for signal handler
_state_manager = None
_interrupt_received = False

def signal_handler(signum, frame):
    """Graceful shutdown on Ctrl+C"""
    global _interrupt_received
    
    # Prevent multiple interrupts causing issues
    if _interrupt_received:
        print("\nForce quitting...")
        os._exit(1)
    
    _interrupt_received = True
    print("\n\nInterrupt received, saving state...")
    
    try:
        if _state_manager:
            _state_manager.complete_run()
            _state_manager.print_summary()
    except Exception as e:
        print(f"Error saving state: {e}")
    
    print("\nState saved. You can resume by running the script again.")
    sys.exit(0)

def process_file_with_state(filepath, detector, refactorer, git_handler, state, feedback_loop=None, args=None):
    """
    Process a single file with full state tracking
    
    Phases:
    1. Detection (smell analysis) 
    2. Refactoring (Gemini)
    3. PR Creation (GitHub)
    
    State is saved after each phase for resume capability
    """
    import sys
    filename = os.path.basename(filepath)
    
    print(f"Starting processing {filename}...", flush=True)
    
    # Start processing
    file_state = state.start_processing(filepath)
    print(f"   Attempts: {file_state['attempts']}/{Config.MAX_RETRIES}", flush=True)
    
    try:
        # ========== PHASE 1: SMELL DETECTION ==========
        if not file_state['detection']['completed']:
            print(f"\nAnalyzing {filename}...", flush=True)
            detection = detector.analyze_file(filepath)
            
            has_smells = detection['result'].get('has_smells', False)
            state.mark_detection_complete(filepath, has_smells)
            
            if not has_smells:
                print("No smells detected - skipping", flush=True)
                state.mark_skipped(filepath, 'no_smells_detected')
                return
        else:
            # Resume: Detection already done
            print(f"\nDetection already completed for {filename}")
            
            # Reload detection data (simplified - in production could cache this)
            detection = detector.analyze_file(filepath)
            
            if not file_state['detection'].get('has_smells'):
                state.mark_skipped(filepath, 'no_smells_detected')
                return
        
        # ========== PHASE 2A: REFACTOR WITH GEMINI ==========
        if not file_state['refactoring']['gemini']['completed']:
            print(f"\n--- Refactoring with Gemini ---")
            gemini_refactoring = refactorer.refactor(detection, use_model='gemini')
            save_report(detection, gemini_refactoring, f"{Config.OUTPUT_DIR}/gemini")
            
            # Don't mark complete yet - wait for PR creation
        else:
            print(f"\nGemini refactoring already completed for {filename}")
            # Load from disk if needed for PR creation
            gemini_refactoring = None  # Would reload from reports in production
        
        # ========== PHASE 3A: CREATE PR (GEMINI VERSION) ==========
        if not file_state['refactoring']['gemini'].get('pr_number'):
            if gemini_refactoring:  # Only if we just did refactoring
                try:
                    print(f"\n--- Creating Pull Request (Gemini) ---")
                    pr = git_handler.create_pr(gemini_refactoring, filepath)
                    state.mark_refactoring_complete(
                        filepath, 
                        'gemini', 
                        pr_number=pr.number, 
                        pr_url=pr.html_url
                    )
                    
                    # Start feedback monitoring if enabled
                    if feedback_loop:
                        print(f"\nStarting feedback monitoring for PR #{pr.number}...")
                        try:
                            feedback_loop.monitor_pr(pr.number, max_iterations=3, check_interval=args.monitor_interval)
                        except KeyboardInterrupt:
                            print(f"\nFeedback monitoring interrupted for PR #{pr.number}")
                        except Exception as e:
                            print(f"Feedback monitoring failed: {e}")
                
                except Exception as e:
                    print(f"Failed to create PR: {e}")
                    # Still mark refactoring as complete, but no PR
                    state.mark_refactoring_complete(filepath, 'gemini')
        else:
            pr_number = file_state['refactoring']['gemini']['pr_number']
            print(f"\nPR already created: #{pr_number}")
            
            # Monitor existing PR if enabled
            if feedback_loop:
                print(f"Monitoring existing PR #{pr_number} for feedback...")
                try:
                    feedback_loop.monitor_pr(pr_number, max_iterations=3, check_interval=args.monitor_interval)
                except KeyboardInterrupt:
                    print(f"\nFeedback monitoring interrupted for PR #{pr_number}")
                except Exception as e:
                    print(f"Feedback monitoring failed: {e}")
        
        # ========== ALL PHASES COMPLETE ==========
        state.mark_completed(filepath)
    
    except Exception as e:
        # Determine which phase failed
        phase = 'detection'
        if file_state['detection']['completed']:
            if not file_state['refactoring']['gemini']['completed']:
                phase = 'refactoring_gemini'
            else:
                phase = 'pr_creation'
        
        print(f"\nERROR in {phase}: {e}")
        state.mark_failed(filepath, str(e), phase)
        
        # Don't crash - continue with next file
        return

def main():
    """
    Main pipeline execution with state management
    """
    global _state_manager
    
    # Parse CLI arguments
    args = parse_args()
    
    print("="*70)
    print("AUTOMATED REFACTORING PIPELINE")
    print("="*70)
    
    # Validate config
    Config.validate()
    
    # Initialize state manager
    if Config.ENABLE_STATE_MANAGEMENT:
        state = StateManager(Config.STATE_FILE, Config.MAX_RETRIES)
        _state_manager = state
        
        # Register signal handler for graceful shutdown
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    else:
        state = None
        print("WARNING: State management disabled")
    
    # Handle CLI commands
    if state and args.reset:
        confirm = input("WARNING: This will delete all progress. Continue? (yes/no): ")
        if confirm.lower() == 'yes':
            state.reset()
            return
        else:
            print("Reset cancelled")
            return
    
    if state and args.stats:
        state.print_summary()
        return
    
    if state and args.failed:
        failed = state.get_failed_files()
        if failed:
            print("\nFailed Files:")
            for f in failed:
                print(f"\n  File: {f['file']}")
                print(f"  Attempts: {f['attempts']}")
                print(f"  Phase: {f['phase']}")
                print(f"  Error: {f['error']}")
        else:
            print("\nNo failed files")
        return
    
    # Show resume info
    if state and state.has_previous_run():
        print(f"\nResuming from previous run...")
        state.print_summary()
        input("\nPress Enter to continue (or Ctrl+C to cancel)...")
    
    # Initialize components
    scanner = FileScanner()
    detector = SmellDetector()
    refactorer = CodeRefactorer()
    git_handler = GitHubHandler()
    
    # Initialize feedback loop if monitoring enabled
    feedback_loop = None
    if args.monitor:
        feedback_loop = FeedbackLoop(git_handler)
        print(f"Feedback monitoring enabled (check interval: {args.monitor_interval}s)")
    
    # Discover files
    files_to_scan = scanner.discover_files()
    
    if not files_to_scan:
        print("WARNING: No files found to scan!")
        return
    
    # Filter files based on state
    remaining_files = []
    skipped_count = 0
    
    for filepath in files_to_scan:
        if state:
            should_process, reason = state.should_process(filepath)
            if not should_process:
                if reason == 'already_completed':
                    skipped_count += 1
                continue
        
        remaining_files.append(filepath)
    
    if skipped_count > 0:
        print(f"\nSkipping {skipped_count} already completed files")
    
    if not remaining_files:
        print("\nAll files already processed!")
        if state:
            state.print_summary()
        return
    
    print(f"\nFiles to process: {len(remaining_files)}")
    
    # Track statistics
    stats = {
        'total_files': len(remaining_files),
        'processed': 0,
        'completed': 0,
        'failed': 0,
        'skipped': 0
    }
    
    # Process each file
    for idx, filepath in enumerate(remaining_files, 1):
        print(f"\n{'='*70}")
        print(f"[{idx}/{len(remaining_files)}] {os.path.relpath(filepath, Config.LOCAL_REPO_PATH)}")
        print(f"{'='*70}")
        
        # Check if file still exists
        if not os.path.exists(filepath):
            print(f"WARNING: File not found, skipping...")
            if state:
                state.mark_skipped(filepath, 'file_not_found')
            stats['skipped'] += 1
            continue
        
        # Process with full error handling

        if state:
            process_file_with_state(filepath, detector, refactorer, git_handler, state, feedback_loop, args)
        else:
            # Original non-state-aware processing
            try:
                detection = detector.analyze_file(filepath)
                
                if not detection['result'].get('has_smells'):
                    print("No smells detected - skipping")
                    stats['skipped'] += 1
                    continue
                
                # Refactor with both models
                gemini_refactoring = refactorer.refactor(detection, use_model='gemini')
                save_report(detection, gemini_refactoring, f"{Config.OUTPUT_DIR}/gemini")
                

                
                # Create PR
                pr = git_handler.create_pr(gemini_refactoring, filepath)
                stats['completed'] += 1
            
            except Exception as e:
                print(f"ERROR: {e}")
                stats['failed'] += 1
        
        stats['processed'] += 1
    
    # Final summary
    if state:
        state.complete_run()
        state.print_summary()
    else:
        print("\n" + "="*70)
        print("PIPELINE SUMMARY")
        print("="*70)
        print(f"Files processed:  {stats['processed']}")
        print(f"Completed:        {stats['completed']}")
        print(f"Failed:           {stats['failed']}")
        print(f"Skipped:          {stats['skipped']}")
        print(f"\nReports saved to:  {Config.OUTPUT_DIR}/")
        print("="*70)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        if _state_manager:
            _state_manager.complete_run()
        sys.exit(1)
    except Exception as e:
        print(f"\nFatal error: {e}")
        if _state_manager:
            _state_manager.complete_run()
        sys.exit(1)
