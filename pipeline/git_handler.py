import os
import hashlib
from github import Github
from config import Config
import time

class GitHubHandler:
    """
    Handles all GitHub operations
    """
    def __init__(self):
        self.g = Github(Config.GITHUB_TOKEN)
        self.repo = self.g.get_repo(Config.GITHUB_REPO)
        print(f"✅ Connected to {Config.GITHUB_REPO}")
    
    def create_pr(self, refactoring_result, original_filepath):
        """
        Create PR with refactored code OR suggestions for multi-file changes
        """
        is_comment_only = refactoring_result.get('is_comment_only', False)
        
        timestamp = int(time.time())
        file_hash = hashlib.md5(original_filepath.encode()).hexdigest()[:8]
        branch_name = f"bot/refactor-{timestamp}-{file_hash}"
        smells = refactoring_result['smells']
        smell_types = [s['type'] for s in smells]
        
        # Get base branch
        base_branch = self.repo.get_branch(self.repo.default_branch)
        
        # Create new branch
        self.repo.create_git_ref(
            ref=f"refs/heads/{branch_name}",
            sha=base_branch.commit.sha
        )
        print(f"Created branch: {branch_name}")
        
        if is_comment_only:
            # Create suggestions file instead of refactored code
            file_path = os.path.relpath(original_filepath, Config.LOCAL_REPO_PATH).replace(os.sep, '/')
            suggestions_file = file_path.replace('.java', '_REFACTORING_SUGGESTIONS.md')
            
            # Format suggestions as markdown
            suggestions_content = f"""# Refactoring Suggestions

**File**: `{file_path}`

## Detected Smells

"""
            for smell in smells:
                suggestions_content += f"""
### {smell['type']} (Severity: {smell['severity']})
- **Location**: Lines {smell.get('line_range', 'N/A')}
- **Evidence**: {smell['evidence']}
- **Affected Methods**: {', '.join(smell.get('affected_methods', []))}
"""
            
            suggestions_content += f"""

## Refactoring Guidance

{refactoring_result.get('suggestions', 'See analysis above')}

---
*This refactoring requires changes to multiple files. Please review and apply manually.*
"""
            
            # Create suggestions file
            self.repo.create_file(
                path=suggestions_file,
                message=f"Add refactoring suggestions for {os.path.basename(file_path)}",
                content=suggestions_content,
                branch=branch_name
            )
            print(f"Created suggestions file: {suggestions_file}")
            
            # Create PR with suggestions
            pr = self.repo.create_pull(
                title=f"[Suggestions] Refactoring guidance for {os.path.basename(file_path)}",
                body=self._generate_pr_body_for_suggestions(refactoring_result, suggestions_file),
                head=branch_name,
                base=self.repo.default_branch
            )
        else:
            # Update files with refactored code (existing logic)
            for fname, code in refactoring_result['refactored_files'].items():
                # Determine file path
                if fname == 'main':
                    file_path = os.path.relpath(original_filepath, Config.LOCAL_REPO_PATH)
                else:
                    # New helper class - put in same directory
                    dir_path = os.path.dirname(os.path.relpath(original_filepath, Config.LOCAL_REPO_PATH))
                    file_path = os.path.join(dir_path, fname)
                
                # Normalize path separators for GitHub
                file_path = file_path.replace(os.sep, '/')
                
                try:
                    # Try to update existing file
                    contents = self.repo.get_contents(file_path, ref=branch_name)
                    self.repo.update_file(
                        path=file_path,
                        message=f"Refactor: Fix {', '.join(smell_types)}",
                        content=code,
                        sha=contents.sha,
                        branch=branch_name
                    )
                    print(f"Updated: {file_path}")
                except Exception as e:
                    # File doesn't exist - create it
                    if "Not Found" in str(e):
                        self.repo.create_file(
                            path=file_path,
                            message=f"Create helper class {fname}",
                            content=code,
                            branch=branch_name
                        )
                        print(f"Created: {file_path}")
                    else:
                        print(f"Failed to update {file_path}: {e}")
                        raise
            
            # Create PR with refactored code
            pr = self.repo.create_pull(
                title=f"Automated Refactoring: Fix {', '.join(smell_types)}",
                body=self._generate_pr_body(refactoring_result),
                head=branch_name,
                base=self.repo.default_branch
            )
        
        print(f"PR Created: {pr.html_url}")
        return pr
    
    
    def _generate_pr_body_for_suggestions(self, refactoring_result, suggestions_file):
        """Generate PR body for comment-only mode"""
        smells = refactoring_result['smells']
        smell_list = ', '.join([s['type'] for s in smells])
        
        body = f"""## Refactoring Suggestions (Multi-File Changes Required)

This code contains design smells that require changes across multiple files. 
Automated refactoring cannot safely be applied.

**Detected Smells**: {smell_list}

### Manual Refactoring Required

Please review the detailed suggestions in `{suggestions_file}`.

The analysis identified dependencies and impacts that span multiple files. 
A human developer should:
1. Review the suggestions
2. Plan the refactoring across affected files
3. Implement changes incrementally
4. Test thoroughly

### Detected Issues

"""
        for smell in smells:
            body += f"""
#### {smell['type']} ({smell['severity']} severity)
- **Location**: Lines {smell.get('line_range', 'N/A')}
- **Impact**: Requires multi-file changes
"""
        
        body += """

---
*Generated by the Automated Refactoring Pipeline*
"""
        return body
    
    def _generate_pr_body(self, refactoring_result):
        """Generate detailed PR description"""
        smells = refactoring_result['smells']
        model = refactoring_result['model_used']
        
        body = f"""## Automated Refactoring

**Model Used:** {model.upper()}

### Detected Design Smells

"""
        for smell in smells:
            body += f"""
#### {smell['type']} ({smell['severity']} severity)
- **Location:** Lines {smell.get('line_range', 'N/A')}
- **Evidence:** {smell['evidence']}
- **Affected Methods:** {', '.join(smell.get('affected_methods', []))}
"""
        
        body += """

### Changes Applied

The refactoring preserves all public interfaces while improving internal structure.

### Review Checklist
- [ ] All tests pass
- [ ] No breaking changes to public API
- [ ] Code is more maintainable
- [ ] Documentation is clear

---
*Generated by the Automated Refactoring Pipeline*
"""
        return body
