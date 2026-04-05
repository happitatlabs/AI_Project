# Description: List all Python scripts in the mellow_link/workspace directory and print their paths using pathlib.

from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent

# List all Python files in the mellow_link/workspace directory
workspace_path = WORKSPACE_ROOT
python_files = workspace_path.rglob("*.py")

# Print the paths of all Python files
for python_file in python_files:
    print(python_file)
