import sys
import os
import subprocess

root_dir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
api_dir = os.path.join(root_dir, "apps", "api")

scripts = [
    ([sys.executable, os.path.join(root_dir, "scripts", "verify_module_07_fix.py")], root_dir),
    ([sys.executable, os.path.join(api_dir, "verify_module_07.py")], api_dir),
    ([sys.executable, os.path.join(api_dir, "verify_module_06.py")], api_dir),
]

for cmd, cwd in scripts:
    print(f"\n>>> Running: {' '.join(cmd)} in {cwd}")
    res = subprocess.run(cmd, cwd=cwd)
    if res.returncode != 0:
        print(f"FAILED: {' '.join(cmd)} exited with code {res.returncode}")
        sys.exit(res.returncode)

print("\nALL VERIFICATIONS PASSED SUCCESSFULLY!")
