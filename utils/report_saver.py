#!/usr/bin/env python3
"""
Enhanced save_report with comment-only mode support
"""
import json
import os

def save_report_enhanced(detection, refactoring, output_dir):
    """Save refactoring report with support for comment-only mode"""
    os.makedirs(output_dir, exist_ok=True)
    
    filename = detection['filename'].replace('.java', '')
    
    # Save original
    with open(f"{output_dir}/{filename}_original.java", 'w') as f:
        f.write(detection['code'])
    
    # Check if comment-only mode
    is_comment_only = refactoring.get('is_comment_only', False)
    
    if is_comment_only:
        # Save suggestions file instead of refactored code
        with open(f"{output_dir}/{filename}_refactoring_suggestions.md", 'w') as f:
            f.write(f"# Refactoring Suggestions for {detection['filename']}\\n\\n")
            f.write("**This file requires multi-file changes. Manual refactoring is recommended.**\\n\\n")
            f.write("## Detected Smells\\n\\n")
            for smell in refactoring.get('smells', []):
                f.write(f"- **{smell['type']}** (Severity: {smell['severity']})\\n")
            f.write("\\n## Refactoring Guidance\\n\\n")
            f.write(refactoring.get('suggestions', 'No suggestions provided'))
        print(f"Multi-file refactoring detected - saved suggestions to {output_dir}/{filename}_refactoring_suggestions.md")
    else:
        # Save refactored code
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
        'model_used': refactoring.get('model_used', 'unknown'),
        'is_comment_only': is_comment_only,
        'files_created': list(refactoring.get('refactored_files', {}).keys()) if not is_comment_only else [],
        'has_suggestions': is_comment_only
    }
    
    with open(f"{output_dir}/{filename}_metadata.json", 'w') as f:
        json.dump(metadata, f, indent=2)
    
    return is_comment_only
