import os
import re
import subprocess
import shlex
import httpx
import logging
from typing import Optional, Dict, Any
from uuid import UUID
from pathlib import Path
from sqlalchemy.orm import Session
from services.shared.models import Integration, CodeProject, CodeSession
from services.shared.security import decrypt_secret
from services.agent.config import settings

logger = logging.getLogger("nexus-github")

def get_user_github_token(db: Session, user_id: UUID) -> Optional[str]:
    """Retrieve decrypted GitHub access token for the user, falling back to system token."""
    integration = db.query(Integration).filter(
        Integration.user_id == user_id,
        Integration.provider == "github",
        Integration.status == "active"
    ).first()
    if integration and integration.access_token:
        try:
            return decrypt_secret(integration.access_token)
        except Exception as e:
            logger.error(f"Failed to decrypt user github token: {e}")
    return settings.GITHUB_TOKEN

def parse_github_repo_url(url: str) -> tuple[Optional[str], Optional[str]]:
    """Parse owner and repo name from GitHub repository URL."""
    if not url:
        return None, None
    match = re.search(r"github\.com[:/]([^/]+)/([^/.]+)", url)
    if match:
        return match.group(1), match.group(2)
    return None, None

def create_pull_request(
    db: Session,
    user_id: UUID,
    project: CodeProject,
    session: CodeSession,
    branch_name: str,
    title: str,
    body: str,
) -> Dict[str, Any]:
    """
    Pushes committed changes in the local session workspace to GitHub 
    and creates a Pull Request via GitHub REST API.
    """
    token = get_user_github_token(db, user_id)
    if not token:
        return {"success": False, "error": "GitHub token not configured. Please link GitHub under Settings."}

    owner, repo = parse_github_repo_url(project.repo_url)
    if not owner or not repo:
        return {"success": False, "error": f"Invalid or non-GitHub repository URL: {project.repo_url}"}

    workspace_root = Path(settings.CODE_WORKSPACE_LOCAL_DIR).expanduser().resolve() / str(session.id)
    if not workspace_root.exists():
        return {"success": False, "error": "Session workspace directory not found."}

    # Setup git credentials for pushing
    remote_url = f"https://x-access-token:{token}@github.com/{owner}/{repo}.git"

    # Git operations
    try:
        # 1. Initialize git if not already initialized
        if not (workspace_root / ".git").exists():
            subprocess.run(["git", "init"], cwd=workspace_root, capture_output=True, check=True)
            subprocess.run(["git", "config", "user.name", "Nexus AI"], cwd=workspace_root, check=True)
            subprocess.run(["git", "config", "user.email", "agent@nexus-ai.com"], cwd=workspace_root, check=True)

        # 2. Check current status
        subprocess.run(["git", "add", "."], cwd=workspace_root, check=True)
        status_res = subprocess.run(["git", "status", "--porcelain"], cwd=workspace_root, capture_output=True, text=True, check=True)
        if not status_res.stdout.strip():
            return {"success": False, "error": "No changes to commit. Working tree is clean."}

        # 3. Checkout branch
        subprocess.run(["git", "checkout", "-b", branch_name], cwd=workspace_root, capture_output=True)

        # 4. Commit changes
        commit_msg = f"Nexus AI: {title}\n\n{body}"
        subprocess.run(["git", "commit", "-m", commit_msg], cwd=workspace_root, check=True)

        # 5. Push to GitHub
        logger.info(f"Pushing branch {branch_name} to GitHub remote...")
        subprocess.run(["git", "push", "-f", remote_url, f"{branch_name}:{branch_name}"], cwd=workspace_root, capture_output=True, check=True)
    except subprocess.CalledProcessError as e:
        stderr = e.stderr or str(e)
        logger.error(f"Git command failed during PR push: {stderr}")
        return {"success": False, "error": f"Git operation failed: {stderr}"}

    # 6. Call GitHub REST API to create Pull Request
    api_url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }
    payload = {
        "title": title,
        "body": body,
        "head": branch_name,
        "base": project.default_branch or "main",
    }

    try:
        with httpx.Client() as client:
            resp = client.post(api_url, headers=headers, json=payload)
            if resp.status_code == 201:
                pr_data = resp.json()
                return {
                    "success": True,
                    "pr_url": pr_data.get("html_url"),
                    "pr_number": pr_data.get("number"),
                    "title": title,
                }
            else:
                err_msg = resp.json().get("message", resp.text)
                logger.error(f"GitHub PR creation failed ({resp.status_code}): {err_msg}")
                return {"success": False, "error": f"GitHub API error: {err_msg}"}
    except Exception as e:
        logger.error(f"Failed to submit PR to GitHub: {e}")
        return {"success": False, "error": f"Failed to submit PR via API: {str(e)}"}
