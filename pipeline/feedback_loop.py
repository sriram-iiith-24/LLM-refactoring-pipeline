import time
import re
from models.gemini_client import GeminiClient

class FeedbackLoop:
    """
    Handles PR feedback and iterative improvements
    """
    def __init__(self, github_handler):
        self.github = github_handler
        self.gemini = GeminiClient()
    
    def monitor_pr(self, pr_number, max_iterations=3, check_interval=3600):
        """
        Monitor PR for feedback and auto-revise
        
        Args:
            pr_number: PR number to monitor
            max_iterations: Max revision attempts
            check_interval: Seconds between checks (default 1 hour)
        """
        pr = self.github.repo.get_pull(pr_number)
        
        for iteration in range(max_iterations):
            print(f"\n🔄 Feedback Loop - Iteration {iteration + 1}/{max_iterations}")
            print(f"   Checking PR #{pr_number} for feedback...")
            
            # Refresh PR state
            pr.update()
            
            # Check if closed
            if pr.state == "closed":
                if pr.merged:
                    print("✅ PR merged successfully!")
                else:
                    print("❌ PR was closed without merging")
                return
            
            # Get feedback
            feedback = self._extract_feedback(pr)
            
            if not feedback:
                print(f"   No feedback yet. Sleeping {check_interval}s...")
                time.sleep(check_interval)
                continue
            
            print(f"   📝 Found {len(feedback)} feedback comment(s)")
            
            # Generate revision
            revision = self._generate_revision(pr, feedback)
            
            # Update PR
            self._update_pr_branch(pr, revision, iteration + 1)
            
            print(f"   ✅ Revision {iteration + 1} pushed to PR")
        
        print(f"\n⚠️  Reached max iterations ({max_iterations})")
    
    def _extract_feedback(self, pr):
        """Extract all review comments"""
        feedback = []
        
        # Review comments (line-specific)
        for comment in pr.get_review_comments():
            feedback.append({
                'type': 'line_comment',
                'file': comment.path,
                'line': comment.position,
                'comment': comment.body,
                'author': comment.user.login
            })
        
        # General comments
        for comment in pr.get_issue_comments():
            feedback.append({
                'type': 'general_comment',
                'comment': comment.body,
                'author': comment.user.login
            })
        
        return feedback
    
    def _generate_revision(self, pr, feedback):
        """Ask LLM to address feedback for all files"""
        # Get all files from PR
        files = list(pr.get_files())
        
        if not files:
            print("   ⚠️  No files in PR")
            return {}
        
        revisions = {}
        
        # Format feedback
        feedback_text = "\n".join([
            f"- [{fb['author']}] {fb['comment']}" +
            (f" (Line {fb['line']} in {fb['file']})" if fb.get('line') else "")
            for fb in feedback
        ])
        
        # Process each file
        for file_obj in files:
            try:
                current_code = self.github.repo.get_contents(
                    file_obj.filename,
                    ref=pr.head.ref
                ).decoded_content.decode()
                
                # Ask Gemini to revise
                prompt = f"""
You previously refactored code, but received this feedback from human reviewers:

FEEDBACK:
{feedback_text}

CURRENT FILE: {file_obj.filename}

CURRENT CODE:
{current_code}

Please revise the code to address ALL feedback points.
- Explain changes in comments
- Maintain all previous improvements
- Return ONLY the complete, updated code without markdown formatting
"""
                
                revised = self.gemini.generate(prompt, model_type='pro', temperature=0.3)
                revisions[file_obj.filename] = self._clean_code(revised)
                
            except Exception as e:
                print(f"   ⚠️  Failed to revise {file_obj.filename}: {e}")
                continue
        
        return revisions
    
    def _clean_code(self, code):
        """Remove markdown artifacts"""
        code = re.sub(r'```java\s*', '', code)
        code = re.sub(r'```\s*', '', code)
        return code.strip()
    
    def _update_pr_branch(self, pr, revisions, iteration):
        """Update the PR branch with revised code for all files"""
        if not revisions:
            print("   ⚠️  No revisions to apply")
            return
        
        branch_name = pr.head.ref
        updated_files = []
        
        # Update each file
        for filename, new_code in revisions.items():
            try:
                contents = self.github.repo.get_contents(filename, ref=branch_name)
                self.github.repo.update_file(
                    path=filename,
                    message=f"🤖 Revision {iteration}: Address reviewer feedback",
                    content=new_code,
                    sha=contents.sha,
                    branch=branch_name
                )
                updated_files.append(filename)
                print(f"   ✓ Updated: {filename}")
            except Exception as e:
                print(f"   ✗ Failed to update {filename}: {e}")
        
        # Add comment to PR
        if updated_files:
            files_list = "\n".join([f"- `{f}`" for f in updated_files])
            pr.create_issue_comment(f"""
🤖 **Automated Revision Applied (Iteration {iteration})**

I've updated the following files to address the feedback provided:

{files_list}

Key changes:
- Incorporated reviewer suggestions
- Maintained previous improvements
- Added explanatory comments

Please re-review when convenient.
""")
