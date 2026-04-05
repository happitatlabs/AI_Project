# Description: List all Python files in the mellow_link/workspace directory and print their paths.

from pathlib import Path

workspace_path = Path(__file__).resolve().parent

for py_file in workspace_path.rglob('*.py'):
    print(py_file)
