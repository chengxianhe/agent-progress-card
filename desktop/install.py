"""Install the reviewed local app without overwriting existing apps or preferences."""

import shutil
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source = root / "build/微光.app"
target = Path.home() / "Applications/微光.app"
subprocess.run(["codesign", "--verify", "--strict", str(source)], check=True)
legacy = Path.home() / "Applications/AgentProgressCard.app"
if target.exists() or target.is_symlink() or legacy.exists() or legacy.is_symlink():
    raise SystemExit("微光或旧名应用已存在，未覆盖；请按迁移说明受控更新。")
target.parent.mkdir(parents=True, exist_ok=True)
shutil.copytree(source, target)
subprocess.run(["codesign", "--verify", "--strict", str(target)], check=True)
print(target)
