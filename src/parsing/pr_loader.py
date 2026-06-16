"""Loads a local file or directory into the list[FileInput] shape run_review() expects."""
import os

EXT_LANG = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".go": "go",
}


def load_directory(path: str) -> list[dict]:
    """Walk a directory recursively, returning every file with a supported extension."""
    files = []
    for root, _dirs, filenames in os.walk(path):
        for filename in filenames:
            ext = os.path.splitext(filename)[1]
            if ext not in EXT_LANG:
                continue
            full_path = os.path.join(root, filename)
            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()
            files.append({
                "path": full_path,
                "content": content,
                "language": EXT_LANG[ext],
            })
    return files


def load_path(path: str) -> list[dict]:
    """Entry point that works for either a single file or a directory."""
    if os.path.isdir(path):
        return load_directory(path)

    ext = os.path.splitext(path)[1]
    if ext not in EXT_LANG:
        raise ValueError(f"Unsupported file type: {ext}")

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    return [{"path": path, "content": content, "language": EXT_LANG[ext]}]
