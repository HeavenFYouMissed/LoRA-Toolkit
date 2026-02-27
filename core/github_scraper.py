"""
GitHub Scraper - Specialized scraper for GitHub repos, files, and pages.

GitHub renders code with JavaScript, so normal scrapers see nothing useful.
This module uses raw.githubusercontent.com and the GitHub API to get the
actual content — README files, source code, issues, etc.
"""
import re
import requests
from config import REQUEST_TIMEOUT, USER_AGENT
from bs4 import BeautifulSoup


# ─── URL Parsing ────────────────────────────────────────────────

def is_github_url(url):
    """Check if a URL is a GitHub page we can handle."""
    return bool(re.match(r'https?://(www\.)?github\.com/', url))


def parse_github_url(url):
    """
    Parse a GitHub URL into components.
    Returns dict: {owner, repo, type, branch, path}
    
    Types: 'repo', 'blob' (file), 'tree' (folder), 'issues', 'issue',
           'pull', 'wiki', 'readme', 'raw', 'other'
    """
    url = url.rstrip("/")
    # Remove query string and fragment
    clean = url.split("?")[0].split("#")[0]
    
    match = re.match(r'https?://(?:www\.)?github\.com/([^/]+)/([^/]+)(?:/(.*))?', clean)
    if not match:
        return None

    owner = match.group(1)
    repo = match.group(2)
    rest = match.group(3) or ""

    info = {"owner": owner, "repo": repo, "type": "repo", "branch": "main", "path": ""}

    if not rest:
        info["type"] = "repo"
    elif rest.startswith("blob/"):
        # github.com/owner/repo/blob/main/path/to/file.py
        info["type"] = "blob"
        parts = rest[5:]  # remove 'blob/'
        slash_idx = parts.find("/")
        if slash_idx >= 0:
            info["branch"] = parts[:slash_idx]
            info["path"] = parts[slash_idx + 1:]
        else:
            info["branch"] = parts
    elif rest.startswith("tree/"):
        info["type"] = "tree"
        parts = rest[5:]
        slash_idx = parts.find("/")
        if slash_idx >= 0:
            info["branch"] = parts[:slash_idx]
            info["path"] = parts[slash_idx + 1:]
        else:
            info["branch"] = parts
    elif rest.startswith("issues/"):
        num = rest.replace("issues/", "").strip("/")
        if num.isdigit():
            info["type"] = "issue"
            info["path"] = num
        else:
            info["type"] = "issues"
    elif rest.startswith("pull/"):
        info["type"] = "pull"
        info["path"] = rest.replace("pull/", "").split("/")[0]
    elif rest.startswith("wiki"):
        info["type"] = "wiki"
        info["path"] = rest.replace("wiki/", "").replace("wiki", "")
    elif rest == "raw":
        info["type"] = "raw"
    else:
        info["type"] = "other"
        info["path"] = rest

    return info


# ─── Content Fetchers ──────────────────────────────────────────

def _headers():
    return {
        "User-Agent": USER_AGENT,
        "Accept": "application/vnd.github.v3+json",
    }


def _raw_url(owner, repo, branch, path):
    """Build raw.githubusercontent.com URL."""
    return f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"


def scrape_github_file(owner, repo, branch, path):
    """
    Fetch a single file's raw content from GitHub.
    Returns {title, content, success, error}
    """
    result = {"title": "", "content": "", "success": False, "error": ""}

    raw = _raw_url(owner, repo, branch, path)
    try:
        resp = requests.get(raw, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200:
            filename = path.split("/")[-1] if "/" in path else path
            ext = filename.rsplit(".", 1)[-1] if "." in filename else ""
            
            result["title"] = f"{owner}/{repo}: {path}"
            
            # Wrap code in a labeled block
            content_parts = [
                f"# File: {owner}/{repo}/{path}",
                f"# Branch: {branch}",
                f"# Source: https://github.com/{owner}/{repo}/blob/{branch}/{path}",
                "",
            ]
            
            if ext in ("md", "markdown", "txt", "rst", ""):
                content_parts.append(resp.text)
            else:
                content_parts.append(f"```{ext}")
                content_parts.append(resp.text)
                content_parts.append("```")
            
            result["content"] = "\n".join(content_parts)
            result["success"] = True
        elif resp.status_code == 404:
            # Try 'master' branch if 'main' failed
            if branch == "main":
                return scrape_github_file(owner, repo, "master", path)
            result["error"] = f"File not found: {path} (tried main and master branches)"
        else:
            result["error"] = f"GitHub returned HTTP {resp.status_code}"
    except Exception as e:
        result["error"] = f"Error fetching file: {e}"

    return result


def scrape_github_repo(owner, repo):
    """
    Fetch repo overview: README + repo description + file tree.
    This is the main entry point for github.com/owner/repo URLs.
    """
    result = {"title": "", "content": "", "success": False, "error": ""}

    content_parts = []

    # 1) Repo info via API (description, stars, language)
    try:
        api_url = f"https://api.github.com/repos/{owner}/{repo}"
        resp = requests.get(api_url, headers=_headers(), timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            result["title"] = f"{owner}/{repo}: {data.get('description', repo)}"
            
            content_parts.append(f"# {owner}/{repo}")
            if data.get("description"):
                content_parts.append(f"\n{data['description']}")
            
            meta = []
            if data.get("language"):
                meta.append(f"Language: {data['language']}")
            if data.get("stargazers_count"):
                meta.append(f"Stars: {data['stargazers_count']:,}")
            if data.get("forks_count"):
                meta.append(f"Forks: {data['forks_count']:,}")
            if data.get("topics"):
                meta.append(f"Topics: {', '.join(data['topics'])}")
            if data.get("license") and data["license"].get("name"):
                meta.append(f"License: {data['license']['name']}")
            
            if meta:
                content_parts.append("\n" + " | ".join(meta))
        else:
            result["title"] = f"{owner}/{repo}"
            content_parts.append(f"# {owner}/{repo}")
    except Exception:
        result["title"] = f"{owner}/{repo}"
        content_parts.append(f"# {owner}/{repo}")

    # 2) File tree via API (top-level only)
    try:
        tree_url = f"https://api.github.com/repos/{owner}/{repo}/contents/"
        resp = requests.get(tree_url, headers=_headers(), timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200:
            files = resp.json()
            if isinstance(files, list):
                content_parts.append("\n--- Repository Files ---")
                for f in sorted(files, key=lambda x: (x.get("type", "") != "dir", x.get("name", ""))):
                    icon = "📁" if f.get("type") == "dir" else "📄"
                    content_parts.append(f"  {icon} {f['name']}")
    except Exception:
        pass

    # 3) README (the main content)
    readme_fetched = False
    for readme_name in ["README.md", "README.rst", "README.txt", "README", "readme.md"]:
        try:
            raw = _raw_url(owner, repo, "main", readme_name)
            resp = requests.get(raw, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                content_parts.append(f"\n--- README ({readme_name}) ---\n")
                content_parts.append(resp.text)
                readme_fetched = True
                break
        except Exception:
            continue

    # Try master branch if main didn't work
    if not readme_fetched:
        for readme_name in ["README.md", "README.rst", "README.txt", "README", "readme.md"]:
            try:
                raw = _raw_url(owner, repo, "master", readme_name)
                resp = requests.get(raw, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
                if resp.status_code == 200:
                    content_parts.append(f"\n--- README ({readme_name}) ---\n")
                    content_parts.append(resp.text)
                    readme_fetched = True
                    break
            except Exception:
                continue

    if content_parts:
        result["content"] = "\n".join(content_parts)
        result["success"] = True
    else:
        result["error"] = "Could not fetch any content from this repository"

    return result


def scrape_github_folder(owner, repo, branch, path):
    """
    Fetch all files in a GitHub folder (non-recursive, code files only).
    Concatenates all code files into one output.
    """
    result = {"title": "", "content": "", "success": False, "error": ""}

    try:
        api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}?ref={branch}"
        resp = requests.get(api_url, headers=_headers(), timeout=REQUEST_TIMEOUT)
        
        if resp.status_code != 200:
            if branch == "main":
                return scrape_github_folder(owner, repo, "master", path)
            result["error"] = f"Could not list folder: HTTP {resp.status_code}"
            return result

        files = resp.json()
        if not isinstance(files, list):
            result["error"] = "Not a folder"
            return result

        result["title"] = f"{owner}/{repo}/{path}"
        
        # Only fetch text/code files, skip binaries
        code_extensions = {
            ".py", ".js", ".ts", ".tsx", ".jsx", ".c", ".cpp", ".h", ".hpp",
            ".cs", ".java", ".lua", ".rb", ".go", ".rs", ".swift", ".kt",
            ".md", ".txt", ".rst", ".json", ".yaml", ".yml", ".toml",
            ".html", ".css", ".scss", ".xml", ".sh", ".bat", ".ps1",
            ".cfg", ".ini", ".env", ".gitignore", ".dockerfile",
        }
        
        content_parts = [f"# Folder: {owner}/{repo}/{path} (branch: {branch})\n"]
        files_fetched = 0
        
        for f in sorted(files, key=lambda x: x.get("name", "")):
            if f.get("type") != "file":
                content_parts.append(f"📁 {f['name']}/")
                continue
            
            name = f.get("name", "")
            ext = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
            
            # Skip large/binary files
            size = f.get("size", 0)
            if size > 500_000:  # >500KB, probably not text
                content_parts.append(f"# Skipped: {name} ({size:,} bytes — too large)")
                continue
            
            if ext not in code_extensions and name.lower() not in {"makefile", "dockerfile", "license", "readme"}:
                content_parts.append(f"# Skipped: {name} (binary/unsupported type)")
                continue
            
            # Fetch raw content
            try:
                raw = _raw_url(owner, repo, branch, f"{path}/{name}")
                file_resp = requests.get(raw, headers={"User-Agent": USER_AGENT}, timeout=10)
                if file_resp.status_code == 200:
                    lang = ext.lstrip(".") if ext else ""
                    content_parts.append(f"\n{'='*60}")
                    content_parts.append(f"# File: {name}")
                    content_parts.append(f"{'='*60}")
                    if lang and lang not in ("md", "txt", "rst"):
                        content_parts.append(f"```{lang}")
                        content_parts.append(file_resp.text)
                        content_parts.append("```")
                    else:
                        content_parts.append(file_resp.text)
                    files_fetched += 1
            except Exception:
                content_parts.append(f"# Error fetching: {name}")
        
        content_parts.insert(1, f"# Fetched {files_fetched} files\n")
        result["content"] = "\n".join(content_parts)
        result["success"] = True

    except Exception as e:
        result["error"] = f"Error: {e}"

    return result


def scrape_github_issue(owner, repo, issue_num):
    """Fetch a GitHub issue/PR with all comments."""
    result = {"title": "", "content": "", "success": False, "error": ""}

    try:
        # Issue details
        api_url = f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_num}"
        resp = requests.get(api_url, headers=_headers(), timeout=REQUEST_TIMEOUT)
        
        if resp.status_code != 200:
            result["error"] = f"Issue not found: HTTP {resp.status_code}"
            return result
        
        issue = resp.json()
        
        kind = "Pull Request" if issue.get("pull_request") else "Issue"
        result["title"] = f"{owner}/{repo} #{issue_num}: {issue.get('title', '')}"
        
        parts = [
            f"# [{kind} #{issue_num}] {issue.get('title', '')}",
            f"Repo: {owner}/{repo}",
            f"Author: {issue.get('user', {}).get('login', 'unknown')}",
            f"State: {issue.get('state', 'unknown')}",
            f"Created: {issue.get('created_at', '')[:10]}",
        ]
        
        if issue.get("labels"):
            labels = [l.get("name", "") for l in issue["labels"]]
            parts.append(f"Labels: {', '.join(labels)}")
        
        parts.append(f"\n--- Body ---\n{issue.get('body', '(no body)')}")
        
        # Fetch comments
        if issue.get("comments", 0) > 0:
            comments_url = f"{api_url}/comments"
            cresp = requests.get(comments_url, headers=_headers(), timeout=REQUEST_TIMEOUT)
            if cresp.status_code == 200:
                comments = cresp.json()
                parts.append(f"\n--- Comments ({len(comments)}) ---")
                for i, comment in enumerate(comments, 1):
                    author = comment.get("user", {}).get("login", "unknown")
                    date = comment.get("created_at", "")[:10]
                    body = comment.get("body", "")
                    parts.append(f"\n[Comment {i}] {author} ({date}):\n{body}")
        
        result["content"] = "\n".join(parts)
        result["success"] = True

    except Exception as e:
        result["error"] = f"Error: {e}"

    return result


# ─── Main Entry Point ──────────────────────────────────────────

def scrape_github(url):
    """
    Main entry point — auto-detect GitHub URL type and scrape accordingly.
    Returns standard {title, content, url, success, error} dict.
    """
    info = parse_github_url(url)
    if not info:
        return {"title": "", "content": "", "url": url, "success": False,
                "error": "Could not parse GitHub URL"}

    owner = info["owner"]
    repo = info["repo"]

    if info["type"] == "repo":
        result = scrape_github_repo(owner, repo)
    elif info["type"] == "blob":
        result = scrape_github_file(owner, repo, info["branch"], info["path"])
    elif info["type"] == "tree":
        result = scrape_github_folder(owner, repo, info["branch"], info["path"])
    elif info["type"] == "issue":
        result = scrape_github_issue(owner, repo, info["path"])
    elif info["type"] == "issues":
        # List of issues — just get the page
        result = scrape_github_repo(owner, repo)
    elif info["type"] == "pull":
        result = scrape_github_issue(owner, repo, info["path"])
    else:
        # Unknown page type — try repo overview as fallback
        result = scrape_github_repo(owner, repo)

    result["url"] = url
    return result
