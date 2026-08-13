import collections
import json
import os
import random
import subprocess
import sys
import threading
import time
import xml.etree.ElementTree as xml_parser
from contextlib import contextmanager

from .utils import ensure_microros_cache, rmtree


GIT_COMMAND_TIMEOUT = 15 * 60
GIT_LOW_SPEED_LIMIT = 1024
GIT_LOW_SPEED_TIME = 30
MAX_FETCH_ATTEMPTS = 5
LOCK_TIMEOUT = 10 * 60


class RepositoryError(RuntimeError):
    pass


def run_git(arguments, env=None, timeout=GIT_COMMAND_TIMEOUT, stream=False):
    command = ['git'] + list(arguments)

    if not stream:
        process = subprocess.Popen(
            command,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
            return -1, stdout, "Git command timed out after {} seconds\n{}".format(timeout, stderr)
        return process.returncode, stdout, stderr

    output_tail = collections.deque(maxlen=80)
    process = subprocess.Popen(
        command,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        bufsize=1,
    )

    def forward_output():
        for line in iter(process.stdout.readline, ''):
            output_tail.append(line)
            sys.stdout.write(line)
            sys.stdout.flush()

    output_thread = threading.Thread(target=forward_output)
    output_thread.daemon = True
    output_thread.start()

    try:
        return_code = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        output_tail.append("Git command timed out after {} seconds\n".format(timeout))
        return_code = -1
    finally:
        output_thread.join(timeout=5)

    return return_code, '', ''.join(output_tail)


@contextmanager
def repository_lock(cache_path, timeout=LOCK_TIMEOUT):
    lock_path = cache_path + '.lock'
    deadline = time.time() + timeout
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)

    while True:
        try:
            os.mkdir(lock_path)
            break
        except FileExistsError:
            if time.time() >= deadline:
                raise RepositoryError(
                    "Timed out waiting for repository cache lock: {}. "
                    "If no other build is running, remove this lock directory.".format(lock_path)
                )
            time.sleep(1)

    try:
        yield
    finally:
        try:
            os.rmdir(lock_path)
        except OSError:
            pass


class Package:
    def __init__(self, name, path):
        self.name = name
        self.path = path
        self.ignored = False

    def ignore(self):
        self.ignored = True
        ignore_path = os.path.join(self.path, 'COLCON_IGNORE')
        with open(ignore_path, 'a'):
            os.utime(ignore_path, None)


class Repository:
    def __init__(self, name, urls, distribution, branch=None):
        self.name = name
        self.urls = [urls] if isinstance(urls, str) else list(urls)
        self.distribution = distribution
        self.branch = distribution if branch is None else branch
        self.path = None
        self.commit = None

        if not self.urls:
            raise ValueError("Repository {} has no download URL".format(name))

    def checkout(self, folder, cache_root, env=None, update=False, offline=False):
        self.path = os.path.join(folder, self.name)
        cache_path = os.path.join(cache_root, 'git', self.distribution, self.name + '.git')
        ensure_microros_cache(cache_root)

        with repository_lock(cache_path):
            self._ensure_bare_cache(cache_path, env)
            cached_commit = self._get_cached_commit(cache_path, env)

            if cached_commit is None:
                if offline:
                    raise RepositoryError(
                        "{} is not available in the local cache and offline mode is enabled".format(self.name)
                    )
                commit = self._fetch_with_retry(cache_path, env)
            elif update and not offline:
                try:
                    commit = self._fetch_with_retry(cache_path, env)
                except RepositoryError as error:
                    print("Warning: {}. Using cached {} @ {}".format(error, self.name, cached_commit[:12]))
                    commit = cached_commit
            else:
                commit = cached_commit

            self._create_worktree(cache_path, self.path, commit, env)
            self.commit = commit

        return commit

    def _cache_ref(self):
        return 'refs/microros/' + self.branch

    def _git(self, arguments, env=None, stream=False, check=True):
        result, stdout, stderr = run_git(arguments, env=env, stream=stream)
        if check and result != 0:
            message = stderr.strip() or stdout.strip() or 'unknown Git error'
            raise RepositoryError(message)
        return result, stdout.strip(), stderr.strip()

    def _ensure_bare_cache(self, cache_path, env):
        if os.path.exists(cache_path):
            result, stdout, _ = self._git(
                ['--git-dir', cache_path, 'rev-parse', '--is-bare-repository'],
                env=env,
                check=False,
            )
            if result == 0 and stdout == 'true':
                return

            print("Removing invalid repository cache: {}".format(cache_path))
            if os.path.isdir(cache_path):
                rmtree(cache_path)
            else:
                os.remove(cache_path)

        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        self._git(['init', '--bare', cache_path], env=env)

    def _get_cached_commit(self, cache_path, env):
        result, stdout, _ = self._git(
            ['--git-dir', cache_path, 'rev-parse', '--verify', self._cache_ref() + '^{commit}'],
            env=env,
            check=False,
        )
        return stdout if result == 0 else None

    def _fetch_once(self, cache_path, url, env):
        refspec = '+refs/heads/{0}:{1}'.format(self.branch, self._cache_ref())
        arguments = [
            '-c', 'http.lowSpeedLimit={}'.format(GIT_LOW_SPEED_LIMIT),
            '-c', 'http.lowSpeedTime={}'.format(GIT_LOW_SPEED_TIME),
            '--git-dir', cache_path,
            'fetch', '--force', '--prune', '--depth=1', '--no-tags',
            url, refspec,
        ]
        result, _, stderr = self._git(arguments, env=env, stream=True, check=False)
        if result != 0:
            raise RepositoryError(stderr or 'git fetch failed')

        commit = self._get_cached_commit(cache_path, env)
        if commit is None:
            raise RepositoryError("Fetched {} but could not resolve {}".format(self.name, self._cache_ref()))
        return commit

    def _fetch_with_retry(self, cache_path, env):
        last_error = None

        for attempt in range(MAX_FETCH_ATTEMPTS):
            url_index = (attempt // 2) % len(self.urls)
            url = self.urls[url_index]
            print(
                "Fetching {} ({}/{}) from {}".format(
                    self.name, attempt + 1, MAX_FETCH_ATTEMPTS, url
                )
            )
            try:
                commit = self._fetch_once(cache_path, url, env)
                print("\t - Cached {} @ {}".format(self.name, commit[:12]))
                return commit
            except RepositoryError as error:
                last_error = error
                print("\t - Fetch failed: {}".format(error))

            if attempt + 1 < MAX_FETCH_ATTEMPTS:
                delay = min(2 ** (attempt + 1), 16) + random.uniform(0, 0.5)
                print("\t - Retrying in {:.1f} seconds".format(delay))
                time.sleep(delay)

        raise RepositoryError(
            "Failed to fetch {} branch {} after {} attempts: {}".format(
                self.name, self.branch, MAX_FETCH_ATTEMPTS, last_error
            )
        )

    def _create_worktree(self, cache_path, worktree_path, commit, env):
        self._git(['--git-dir', cache_path, 'worktree', 'prune'], env=env)

        if os.path.exists(worktree_path):
            self._git(
                ['--git-dir', cache_path, 'worktree', 'remove', '--force', worktree_path],
                env=env,
                check=False,
            )
            if os.path.isdir(worktree_path):
                rmtree(worktree_path)
            elif os.path.exists(worktree_path):
                os.remove(worktree_path)
            self._git(['--git-dir', cache_path, 'worktree', 'prune'], env=env)

        os.makedirs(os.path.dirname(worktree_path), exist_ok=True)
        self._git(
            ['--git-dir', cache_path, 'worktree', 'add', '--force', '--detach', worktree_path, commit],
            env=env,
        )

    def get_packages(self):
        packages = []
        if os.path.exists(os.path.join(self.path, 'package.xml')):
            packages.append(Package(self.name, self.path))
        else:
            for root, dirs, files in os.walk(self.path):
                if 'package.xml' in files:
                    package_name = Repository.get_package_name_from_package_xml(
                        os.path.join(root, 'package.xml')
                    )
                    packages.append(Package(package_name, os.path.abspath(root)))
                elif 'colcon.pkg' in files:
                    package_name = Repository.get_package_name_from_colcon_pkg(
                        os.path.join(root, 'colcon.pkg')
                    )
                    packages.append(Package(package_name, os.path.abspath(root)))
        return packages

    @classmethod
    def get_package_name_from_package_xml(cls, xml_file):
        root_node = xml_parser.parse(xml_file).getroot()
        name_node = root_node.find('name')
        if name_node is not None:
            return name_node.text
        return None

    @classmethod
    def get_package_name_from_colcon_pkg(cls, colcon_pkg):
        with open(colcon_pkg, 'r') as file:
            content = json.load(file)
            return content.get('name')


class Sources:
    GITEE_PREFIX = 'https://gitee.com/rtt-microros-mirror'
    GITHUB_PREFIX = 'https://github.com/RT-MicroROS'

    DEV_REPOSITORIES = [
        'ament_cmake',
        'ament_lint',
        'ament_package',
        'googletest',
        'ament_cmake_ros',
        'ament_index',
    ]

    MCU_REPOSITORIES = {
        'humble': [
            ('Micro-CDR', 'ros2'),
            ('Micro-XRCE-DDS-Client', 'ros2'),
            ('rcl', None),
            ('rclc', None),
            ('micro_ros_utilities', None),
            ('rcutils', None),
            ('micro_ros_msgs', None),
            ('rmw_microxrcedds', None),
            ('rosidl_typesupport', None),
            ('rosidl_typesupport_microxrcedds', None),
            ('rosidl', None),
            ('rmw', None),
            ('rcl_interfaces', None),
            ('rosidl_defaults', None),
            ('unique_identifier_msgs', None),
            ('common_interfaces', None),
            ('test_interface_files', None),
            ('rmw_implementation', None),
            ('rcl_logging', None),
            ('ros2_tracing', None),
        ],
        'foxy': [
            ('Micro-CDR', 'ros2'),
            ('Micro-XRCE-DDS-Client', 'foxy-bb'),
            ('rcl', None),
            ('rclc', None),
            ('rcutils', None),
            ('micro_ros_msgs', None),
            ('rmw_microxrcedds', None),
            ('rosidl_typesupport', None),
            ('rosidl_typesupport_microxrcedds', None),
            ('tinydir_vendor', 'master'),
            ('rosidl', None),
            ('rmw', None),
            ('rcl_interfaces', None),
            ('rosidl_defaults', None),
            ('unique_identifier_msgs', None),
            ('common_interfaces', None),
            ('test_interface_files', None),
            ('rmw_implementation', None),
            ('rcl_logging', None),
            ('ros2_tracing', 'foxy_microros'),
        ],
    }

    ignore_packages = {
        'humble': ['rcl_logging_log4cxx', 'rcl_logging_spdlog', 'rcl_yaml_param_parser', 'rclc_examples'],
        'foxy': [
            'rosidl_typesupport_introspection_c',
            'rosidl_typesupport_introspection_cpp',
            'rcl_logging_log4cxx',
            'rcl_logging_spdlog',
            'rcl_yaml_param_parser',
            'rclc_examples',
        ],
    }

    @classmethod
    def _mirror_urls(cls, name, preferred_mirror):
        urls = {
            'gitee': cls.GITEE_PREFIX + '/' + name,
            'github': cls.GITHUB_PREFIX + '/' + name,
        }
        secondary = 'github' if preferred_mirror == 'gitee' else 'gitee'
        return [urls[preferred_mirror], urls[secondary]]

    @classmethod
    def dev_environment(cls, distro, preferred_mirror):
        return [
            Repository(name, cls._mirror_urls(name, preferred_mirror), distro)
            for name in cls.DEV_REPOSITORIES
        ]

    @classmethod
    def mcu_environment(cls, distro, preferred_mirror):
        repositories = []
        for name, branch in cls.MCU_REPOSITORIES[distro]:
            if distro == 'foxy' and name == 'Micro-XRCE-DDS-Client':
                urls = ['https://gitee.com/kurisaW/Micro-XRCE-DDS-Client']
            elif distro == 'foxy' and name == 'ros2_tracing':
                urls = ['https://gitlab.com/micro-ROS/ros_tracing/ros2_tracing']
            else:
                urls = cls._mirror_urls(name, preferred_mirror)
            repositories.append(Repository(name, urls, distro, branch))
        return repositories

