from subprocess import PIPE, run
import os
import stat
import json
import platform
import re
import shutil
import subprocess

def run_cmd(command, env=None, capture_output=False, cwd=None):
    if capture_output:
        result = run(command, shell=True, env=env, stdout=PIPE, stderr=PIPE, cwd=cwd, text=True)
        return result.returncode, result.stderr
    else:
        result = run(command, shell=True, env=env, cwd=cwd)
        return result.returncode, None

def rmtree(directory):
    if os.path.isdir(directory):
        for root, dirs, files in os.walk(directory, topdown=False):
            for name in files:
                filepath = os.path.join(root, name)
                os.chmod(filepath, stat.S_IWUSR)
                os.remove(filepath)
            for name in dirs:
                dirpath = os.path.join(root, name)
                if os.path.islink(dirpath):
                    os.unlink(dirpath)
                else:
                    os.chmod(dirpath, stat.S_IWUSR)
                    os.rmdir(dirpath)
        os.chmod(directory, stat.S_IWUSR)
        os.rmdir(directory)

class EnvironmentHandler:
    def __init__(self):
        self.modified_env = os.environ.copy()
        self.python_cmd = None  # Store the detected Python command

    def get_env(self):
        return self.modified_env

    def set_environment_variable(self, variable, value):
        self.modified_env[variable] = value

    def reset_environment(self):
        self.modified_env = os.environ.copy()

    def find_and_set_python3(self):
        """Find Python 3 executable and update PATH accordingly.

        This method tries multiple approaches to find Python 3:
        1. Direct command invocation (python3, python, py -3, py)
        2. Using shutil.which() to locate the executable
        3. Falls back to PATH environment variable search

        Returns:
            bool: True if Python 3 was found and configured, False otherwise
        """
        # Try to find Python 3 executable by testing commands
        python_cmd = None
        python_path = None
        python_dir = None

        # List of possible Python 3 commands to try (in order of preference)
        if platform.system() == "Windows":
            # On Windows, try: python3, python, py -3, py
            commands_to_try = ['python3', 'python', 'py']
        else:
            # On Linux/macOS, try: python3, python
            commands_to_try = ['python3', 'python']

        for cmd in commands_to_try:
            try:
                # Use shutil.which to find the executable
                found_path = shutil.which(cmd)
                if found_path:
                    # Verify it's actually Python 3.x
                    result = subprocess.run(
                        [cmd, '--version'],
                        capture_output=True,
                        text=True,
                        timeout=5,
                        env=self.modified_env
                    )
                    version_output = result.stdout.strip() or result.stderr.strip()

                    # Check if version string contains "Python 3"
                    if 'Python 3.' in version_output or 'Python 3' in version_output:
                        self.python_cmd = cmd
                        python_path = found_path
                        python_dir = os.path.dirname(found_path)
                        print(f"Found Python 3: {python_path}")
                        print(f"Version: {version_output}")
                        break
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError, Exception):
                continue

        # If no Python 3 found, try legacy PATH search as fallback
        if not python_path:
            print("Primary search failed, trying PATH search as fallback...")
            path_sep = ";" if platform.system() == "Windows" else ":"
            path_entries = self.modified_env.get('PATH', '').split(path_sep)

            # Search for Python 3 in PATH (case-insensitive)
            possible_python_paths = [
                x for x in path_entries
                if re.search(r'python3?|Python3?', x, re.IGNORECASE) and "Scripts" not in x
            ]
            print("possible_python_path:", possible_python_paths)

            if possible_python_paths:
                python_dir = possible_python_paths[0]
                python_path = os.path.join(python_dir, 'python3' if platform.system() != "Windows" else 'python.exe')
                self.python_cmd = 'python3' if platform.system() != "Windows" else 'python'
                print(f"Found Python via PATH search: {python_dir}")
            else:
                print("Python 3 not found in PATH")
                return False

        # Update PATH environment variable
        path_sep = ";" if platform.system() == "Windows" else ":"
        current_path = self.modified_env.get('PATH', '').split(path_sep)

        # Add Python directory to PATH if not already present
        if python_dir and python_dir not in current_path:
            current_path.insert(0, python_dir)
            print(f"Added to PATH: {python_dir}")

        # Look for Scripts directory (Windows) or common bin directories (Linux)
        scripts_dir = None
        if platform.system() == "Windows":
            # Check for Scripts directory (common on Windows Python installations)
            potential_scripts = [
                os.path.join(python_dir, 'Scripts'),
                os.path.join(os.path.dirname(python_dir), 'Scripts')
            ]
            for ps in potential_scripts:
                if os.path.isdir(ps):
                    scripts_dir = ps
                    break
        else:
            # On Linux, check for local/bin or similar directories
            parent_dir = os.path.dirname(python_dir)
            if os.path.basename(parent_dir) == 'bin':
                scripts_dir = parent_dir

        # Add Scripts/bin directory to PATH if found
        if scripts_dir and scripts_dir not in current_path:
            current_path.insert(0, scripts_dir)
            print(f"Added to PATH: {scripts_dir}")

        # Update the environment variable
        self.set_environment_variable('PATH', path_sep.join(current_path))

        # Ensure pip is installed
        try:
            result = run_cmd(f'{self.python_cmd} -m ensurepip', env=self.modified_env, capture_output=True)
            # ignore ensurepip errors (pip might already be installed)
        except Exception as e:
            print(f"Note: ensurepip check completed (pip may already be installed)")

        # Set PYTHONPATH if not already set (helps with module discovery)
        if 'PYTHONPATH' not in self.modified_env and python_dir:
            self.set_environment_variable('PYTHONPATH', python_dir)

        return True

    def install_python_dependencies(self, deps):
        # Install dependencies
        # Use detected Python command, or fall back to platform-specific defaults
        python_cmd = self.python_cmd if self.python_cmd else ('python3' if platform.system() != 'Windows' else 'python')
        pip_command = run(f'{python_cmd} -m pip freeze', shell=True, env=self.modified_env, stdout=PIPE, stderr=PIPE, text=True)
        stdout = pip_command.stdout
        pip_packages = [x.split("==")[0] for x in stdout.split('\n') if x]
        required_packages = deps
        to_install = []
        for req in required_packages:
            if req.split('==')[0].lower() not in [y.lower() for y in pip_packages]:
                to_install.append(req)

        if not to_install:
            print("All required Python pip packages are installed")

        for p in to_install:
            print(f'Installing {p} with pip at RT-Thread environment')
            run_cmd(f'{python_cmd} -m pip install {p}', env=self.modified_env, capture_output=False)

class MetaFileGenerator:
    def __init__(self, path):
        self.meta = {"names": {}}
        self.path = path
        self.save()

    def set_variable(self, package, var, value):
        if package not in self.meta["names"]:
            self.meta["names"][package] = {"cmake-args": []}
        self.meta["names"][package]["cmake-args"].append("-D" + var + "=" + str(value))
        self.save()

    def save(self):
        with open(self.path, "w") as file:
            file.write(json.dumps(self.meta, indent=4))
