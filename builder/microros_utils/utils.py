from subprocess import PIPE, run
import os
import stat
import json
import platform
import re
import shutil
import shlex
import subprocess
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

MICROROS_CACHE_MARKER = '.microros-cache'
CHINA_PIP_INDEX_URL = 'https://pypi.tuna.tsinghua.edu.cn/simple'


def quote_python_command(command):
    """Quote a Python executable for a shell command on the current platform."""
    if os.name == 'nt':
        return subprocess.list2cmdline([command])
    return shlex.quote(command)


def detect_china_ip(timeout=2):
    """Return whether the public IP is in China, or ``None`` if unknown.

    The lookup is deliberately best-effort: an unavailable geolocation service
    must never prevent an offline build or force a particular download source.
    ``MICROROS_IP_COUNTRY`` can be used by CI and restricted networks to avoid
    the external lookup (for example, set it to ``CN`` or ``US``).
    """
    country_override = os.environ.get('MICROROS_IP_COUNTRY')
    if country_override:
        return country_override.strip().upper() in ('CN', 'CHINA')

    endpoints = (
        'https://ipapi.co/json/',
        'https://ipinfo.io/json',
    )
    for endpoint in endpoints:
        try:
            request = Request(endpoint, headers={'User-Agent': 'micro-ros-rtthread'})
            with urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode('utf-8'))
            country = (
                payload.get('country_code')
                or payload.get('countryCode')
                or payload.get('country')
            )
            if country:
                return country.strip().upper() == 'CN'
        except (HTTPError, URLError, OSError, ValueError, KeyError):
            continue

    print('Unable to determine public IP region; using default download sources')
    return None

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

def get_default_microros_cache_dir():
    configured_path = os.environ.get('MICROROS_CACHE_DIR')
    if configured_path:
        return os.path.abspath(os.path.expanduser(configured_path))

    if platform.system() == 'Windows':
        cache_home = os.environ.get('LOCALAPPDATA') or os.path.expanduser('~')
    else:
        cache_home = os.environ.get('XDG_CACHE_HOME') or os.path.join(os.path.expanduser('~'), '.cache')

    return os.path.join(cache_home, 'micro_ros_rtthread')

def ensure_microros_cache(cache_dir):
    cache_dir = os.path.abspath(os.path.expanduser(cache_dir))
    os.makedirs(cache_dir, exist_ok=True)
    marker_path = os.path.join(cache_dir, MICROROS_CACHE_MARKER)
    if not os.path.exists(marker_path):
        with open(marker_path, 'w') as marker:
            marker.write('micro-ROS RT-Thread download cache\n')
    return cache_dir

def clean_microros_cache(cache_dir):
    cache_dir = os.path.abspath(os.path.expanduser(cache_dir))
    if not os.path.exists(cache_dir):
        return False

    marker_path = os.path.join(cache_dir, MICROROS_CACHE_MARKER)
    if not os.path.isfile(marker_path):
        raise RuntimeError(
            "Refusing to remove unrecognized micro-ROS cache directory: {}".format(cache_dir)
        )

    rmtree(cache_dir)
    return True

class EnvironmentHandler:
    def __init__(self):
        self.modified_env = os.environ.copy()
        self.python_cmd = None  # Store the detected Python command

    def get_env(self):
        return self.modified_env

    def configure_download_mirrors(self, china_network):
        """Configure pip for China without overriding an explicit user setting."""
        if china_network:
            if not self.modified_env.get('PIP_INDEX_URL'):
                self.set_environment_variable('PIP_INDEX_URL', CHINA_PIP_INDEX_URL)
            print('China IP detected; using the Tsinghua PyPI mirror for dependencies')

    def ensure_cmake(self, minimum_version='3.13'):
        """Check that a usable CMake executable is available in the build env."""
        cmake_path = shutil.which('cmake', path=self.modified_env.get('PATH'))
        if not cmake_path:
            return False

        try:
            result = subprocess.run(
                [cmake_path, '--version'],
                capture_output=True,
                text=True,
                timeout=10,
                env=self.modified_env,
            )
            version_line = (result.stdout or '').splitlines()[0]
            version = tuple(int(part) for part in re.findall(r'\d+', version_line)[:3])
            required = tuple(int(part) for part in minimum_version.split('.'))
            if result.returncode != 0 or version < required:
                return False
        except (OSError, subprocess.SubprocessError, IndexError, ValueError):
            return False

        self.set_environment_variable('MICROROS_CMAKE_EXECUTABLE', cmake_path)
        print('Found CMake: {}'.format(cmake_path))
        return True

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
                        # Keep the absolute path so child build steps use the same
                        # interpreter as pip, even when the Windows `py` launcher
                        # points at a different installation.
                        self.python_cmd = found_path
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
                self.python_cmd = python_path
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
        self.set_environment_variable('MICROROS_PYTHON_EXECUTABLE', python_path)

        # Ensure pip is installed
        try:
            python_command = quote_python_command(self.python_cmd)
            result = run_cmd(f'{python_command} -m ensurepip', env=self.modified_env, capture_output=True)
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
        python_command = quote_python_command(python_cmd)
        pip_command = run(f'{python_command} -m pip freeze', shell=True, env=self.modified_env, stdout=PIPE, stderr=PIPE, text=True)
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
            run_cmd(f'{python_command} -m pip install {p}', env=self.modified_env, capture_output=False)

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

