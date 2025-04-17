from subprocess import PIPE, run
import os
import stat
import json
import platform
import re

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

    def get_env(self):
        return self.modified_env

    def set_environment_variable(self, variable, value):
        self.modified_env[variable] = value

    def reset_environment(self):
        self.modified_env = os.environ.copy()

    def find_and_set_python3(self):
        path_sep = ";" if platform.system() == "Windows" else ":"
        path = self.modified_env['PATH'].split(path_sep)
        
        # Use case-insensitive search for 'python3' in path
        possible_python_path = [x for x in path if re.search(r'python3', x, re.IGNORECASE) and "Scripts" not in x]
        print("possible_python_path:",possible_python_path)

        if len(possible_python_path) >= 1:
            python_script_path = [x for x in path if re.search(r'python3', x, re.IGNORECASE) and "Scripts" in x]
            # Prepend paths to PATH variable
            path.insert(0, possible_python_path[0])
            if python_script_path:
                path.insert(0, python_script_path[0])
            self.set_environment_variable('PATH', path_sep.join(path))
            
            # Check that pip is installed
            python_cmd = 'python3' if platform.system() != 'nt' else 'py -3'
            run_cmd(f'{python_cmd} -m ensurepip', env=self.modified_env, capture_output=True)

            return True
        else:
            return False

    def install_python_dependencies(self, deps):
        # Install dependencies
        python_cmd = 'python3' if platform.system() != 'nt' else 'py -3'
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
