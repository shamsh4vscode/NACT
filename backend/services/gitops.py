import subprocess
from pathlib import Path

REPO = Path("/gitops-infra")

def run(command: list[str]) -> dict:
    proc = subprocess.run(command, cwd=REPO, text=True, capture_output=True)
    return {"returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}

def submit_change(branch: str, files: dict[str, str]) -> dict:
    run(["git", "checkout", "-B", branch])
    for name, content in files.items():
        path = REPO / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        run(["git", "add", str(path)])
    committed = run(["git", "commit", "-m", f"NACT change {branch}"])
    return {"branch": branch, "commit": committed["returncode"] == 0}

def validate() -> dict:
    ansible = run(["ansible-playbook", "--syntax-check", "ansible/playbook.yml"])
    terraform = run(["terraform", "-chdir=terraform", "validate"])
    return {"ansible": ansible["returncode"] == 0, "terraform": terraform["returncode"] == 0}
