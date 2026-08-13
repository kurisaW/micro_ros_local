import rtconfig
import os, sys
import hashlib
import json
import shutil
import stat
import tempfile
from distutils.dir_util import copy_tree

from .utils import quote_python_command, run_cmd, rmtree
from .repositories import RepositoryError, Sources
from .scons_cmake import write_scons_cmake_config


STATIC_ROSIDL_TYPESUPPORT_C = 'rosidl_typesupport_microxrcedds_c'
STATIC_RMW_IMPLEMENTATION = 'rmw_microxrcedds'


class Build:
    def __init__(
        self,
        library_folder,
        packages_folder,
        distro,
        env,
        cache_folder,
        preferred_mirror='gitee',
        update_sources=False,
        offline=False,
        scons_build_config=None,
    ):

        project_id = hashlib.sha256(
            os.path.realpath(library_folder).encode('utf-8')
        ).hexdigest()[:12]
        self.temp_folder = os.path.join(
            tempfile.gettempdir(), 'micro_ros_build', project_id, distro
        )

        self.library_folder = library_folder
        self.packages_folder = packages_folder
        self.build_folder = self.temp_folder
        self.distro = distro
        self.env = env
        self.cache_folder = os.path.abspath(os.path.expanduser(cache_folder))
        self.preferred_mirror = preferred_mirror
        self.update_sources = update_sources
        self.offline = offline
        self.scons_build_config = scons_build_config
        self.scons_cmake_config = os.path.join(
            self.temp_folder, 'rtt_scons_build.cmake'
        )

        self.dev_packages = []
        self.mcu_packages = []

        self.dev_folder = os.path.join(self.build_folder, 'dev')
        self.dev_src_folder = os.path.join(self.dev_folder, 'src')
        self.mcu_folder = os.path.join(self.build_folder, 'mcu')
        self.mcu_src_folder = os.path.join(self.mcu_folder, 'src')
        self.patch_folder = os.path.join(library_folder, 'patchs', self.distro)

        self.library_path = os.path.join(library_folder, 'libmicroros')
        self.library = os.path.join(self.library_path, "libmicroros.a")
        self.includes = os.path.join(self.library_path, 'include')
        self.build_config_stamp = os.path.join(self.library_path, '.build-config.sha256')
        self.library_name = "microros"

    def run(self, toolchain, user_meta=""):
        build_config_digest = self._build_config_digest(toolchain, user_meta)
        existing_digest = None
        if os.path.isfile(self.build_config_stamp):
            with open(self.build_config_stamp, 'r') as stamp_file:
                existing_digest = stamp_file.read().strip()

        library_ready = (
            os.path.isfile(self.library)
            and os.path.isdir(self.includes)
            and existing_digest == build_config_digest
        )
        if library_ready and not self.update_sources:
            print("micro-ROS already built")
            return

        if os.path.exists(self.library_path):
            print("Removing incomplete or configuration-mismatched micro-ROS library")
            rmtree(self.library_path)

        # Delete previous build folders
        rmtree(self.temp_folder)
        os.makedirs(self.temp_folder)

        if self.scons_build_config is None:
            raise RuntimeError("RT-Thread SCons build configuration was not provided")
        write_scons_cmake_config(self.scons_build_config, self.scons_cmake_config)
        print("Generated RT-Thread CMake configuration: {}".format(self.scons_cmake_config))

        try:
            self.download_dev_environment()
            self.apply_patches(self.dev_src_folder)
            self.build_dev_environment()
            self.download_mcu_environment()
            self.download_extra_packages()
            self.apply_patches(self.mcu_src_folder)
            self.build_mcu_environment(toolchain, user_meta)
            self.package_mcu_library()
            with open(self.build_config_stamp, 'w') as stamp_file:
                stamp_file.write(build_config_digest + '\n')
        except RepositoryError as error:
            print("micro-ROS source download failed: {}".format(error))
            sys.exit(1)

        # Delete generated build folders
        # Here we chose to keep the micro-ROS repository source files,too facilitate the debugging of project functions
        # rmtree(self.temp_folder)

    def _build_config_digest(self, toolchain, user_meta):
        digest = hashlib.sha256()
        digest.update(self.distro.encode('utf-8'))
        digest.update(STATIC_ROSIDL_TYPESUPPORT_C.encode('utf-8'))
        digest.update(STATIC_RMW_IMPLEMENTATION.encode('utf-8'))
        digest.update(
            json.dumps(
                self.scons_build_config,
                sort_keys=True,
                separators=(',', ':'),
            ).encode('utf-8')
        )

        common_meta = os.path.join(self.library_folder, 'metas', 'common.meta')
        for config_file in [toolchain, common_meta, user_meta]:
            if config_file and os.path.isfile(config_file):
                with open(config_file, 'rb') as input_file:
                    digest.update(input_file.read())

        return digest.hexdigest()

    def ignore_package(self, name):
        for p in self.mcu_packages:
            if p.name == name:
                p.ignore()

    def apply_patches(self, target_folder):
        for patch_file in [x for x in os.listdir(self.patch_folder) if x.endswith('patch')]:
            repository_name = patch_file.split('.')[0]
            repository_path = os.path.normpath(os.path.join(target_folder, repository_name))

            # Check if repository exists
            if os.path.isdir(repository_path):

                # Apply patch
                patch_path = os.path.join(self.patch_folder, patch_file)

                print(patch_path)
                print(repository_path)

                command =  'patch -p1 < {}'.format(patch_path) if os.name != 'nt' else 'git apply {} --verbose'.format(patch_path)
                result, stderr = run_cmd(command, env=self.env, capture_output=True, cwd=repository_path)

                if result != 0:
                    print("{} repository patch failed: \n{}".format(repository_name, stderr))
                    sys.exit(1)

                print("\t - Patched {}".format(repository_name))

    def download_dev_environment(self):
        print("Downloading micro-ROS dev dependencies")
        for repo in Sources.dev_environment(self.distro, self.preferred_mirror):
            commit = repo.checkout(
                self.dev_src_folder,
                self.cache_folder,
                env=self.env,
                update=self.update_sources,
                offline=self.offline,
            )
            print("\t - Ready {} @ {}".format(repo.name, commit[:12]))
            self.dev_packages.extend(repo.get_packages())

    def build_dev_environment(self):
        print("Building micro-ROS dev dependencies")
        python_cmd = self._python_command()
        command = '{} -m colcon build --packages-ignore-regex=.*_cpp --cmake-args -DBUILD_TESTING=OFF -G "Unix Makefiles"'.format(python_cmd)
        result, stderr = run_cmd(command, env=self.env, cwd=self.dev_folder)

        if result != 0:
            print("Build dev micro-ROS environment failed\n")
            sys.exit(1)

    def download_mcu_environment(self):
        print("Downloading micro-ROS library")
        for repo in Sources.mcu_environment(self.distro, self.preferred_mirror):
            commit = repo.checkout(
                self.mcu_src_folder,
                self.cache_folder,
                env=self.env,
                update=self.update_sources,
                offline=self.offline,
            )
            packages = repo.get_packages()
            self.mcu_packages.extend(packages)
            for package in packages:
                if package.name in Sources.ignore_packages[self.distro] or package.name.endswith("_cpp"):
                    package.ignore()

                print(
                    '\t - Ready {} @ {}{}'.format(
                        package.name,
                        commit[:12],
                        " (ignored)" if package.ignored else "",
                    )
                )

    def download_extra_packages(self):
        if not os.path.exists(self.packages_folder):
            print("\t - Extra packages folder not found, skipping...")
            return

        print("Checking extra packages")

        extra_folders = os.listdir(self.packages_folder)
    
        if '.gitkeep' in extra_folders:
            extra_folders.remove('.gitkeep')

        for folder in extra_folders:
            print("\t - Adding {}".format(folder))

        copy_tree(self.packages_folder, self.mcu_src_folder)

    def build_mcu_environment(self, toolchain_file, user_meta=""):
        print("Building micro-ROS library")
        common_meta_path = os.path.join(self.library_folder, 'metas', 'common.meta')
        python_cmd = self._python_command()
        toolchain_file = os.path.abspath(toolchain_file).replace('\\', '/')
        scons_cmake_config = os.path.abspath(self.scons_cmake_config).replace('\\', '/')
        colcon_command = '{} -m colcon build --merge-install --packages-ignore-regex=.*_cpp --metas {} {} --cmake-args -DCMAKE_INSTALL_LIBDIR=lib -DCMAKE_POSITION_INDEPENDENT_CODE:BOOL=OFF -DTHIRDPARTY=ON -DBUILD_SHARED_LIBS=OFF -DBUILD_TESTING=OFF -DCMAKE_BUILD_TYPE=Release -DRTT_SCONS_CONFIG_FILE={} -DCMAKE_TOOLCHAIN_FILE={} -G "Unix Makefiles"'.format(python_cmd, common_meta_path, user_meta, scons_cmake_config, toolchain_file)
        command = 'cmd /c "{}\\install\\setup.bat && {}"'.format(self.dev_folder, colcon_command) if os.name == 'nt' else "bash -c 'source {}/install/setup.bash; {}'".format(self.dev_folder, colcon_command)
        os.chmod(self.dev_folder, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
        print(command)
        build_env = self.env.copy()
        build_env['RTT_SCONS_CONFIG_FILE'] = scons_cmake_config
        build_env['STATIC_ROSIDL_TYPESUPPORT_C'] = STATIC_ROSIDL_TYPESUPPORT_C
        build_env['RMW_IMPLEMENTATION'] = STATIC_RMW_IMPLEMENTATION
        result, stderr = run_cmd(command, env=build_env, cwd=self.mcu_folder)

        if result != 0:
            print("Build mcu micro-ROS environment failed\n")
            sys.exit(1)

    def _python_command(self):
        """Return the interpreter selected during the environment check."""
        python_executable = self.env.get('MICROROS_PYTHON_EXECUTABLE')
        if not python_executable:
            python_executable = 'python3' if os.name != 'nt' else 'python'
        return quote_python_command(python_executable)

    def package_mcu_library(self):
        aux_folder = os.path.join(self.build_folder, "temp")
        aux_naming_folder = os.path.join(aux_folder, "naming")

        os.makedirs(aux_folder)
        os.makedirs(aux_naming_folder)
        os.makedirs(self.library_path)

        AR = rtconfig.PREFIX + 'ar'
        # Generate object files with namespace prefix
        obj_list = []
        os.chdir(aux_naming_folder)
        for root, dirs, files in os.walk(os.path.join(self.mcu_folder, "install", "lib")):
            for f in files:
                if f.endswith('.a'):
                    os.system("{AR} x {PATH}".format(AR=AR, PATH=os.path.join(root, f)))
                    for obj in [x for x in os.listdir(aux_naming_folder) if x.endswith('obj')]:
                        updated_name = f.split('.')[0] + "__" + obj
                        os.rename(obj, os.path.join('..', updated_name))
                        obj_list.append(updated_name)
                        print("updated_name:" + updated_name)
        print("Save Micro-Ros static libraries to local")

        # Create linker script
        os.chdir(aux_folder)
        # create a ar_script.m file to cover content:$(ar_script.write(content))
        with open("ar_script.m", "w+") as ar_script:
            ar_script.write("CREATE libmicroros.a\n")

            for element in obj_list:
                ar_script.write("ADDMOD {}\n".format(element))

            ar_script.write("SAVE\n")
            ar_script.write("END")

        # Execute linker script
        command = "{} -M < ar_script.m".format(AR)
        result, stderr = run_cmd(command, env=self.env)

        if result != 0:
            print("micro-ROS static library build failed\n")
            sys.exit(1)

        shutil.copy(os.path.join(self.build_folder, "temp", "libmicroros.a"), self.library_path)

        # Copy includes
        shutil.copytree(os.path.join(self.build_folder, "mcu", "install", "include"), self.includes)

        # Fix include paths
        if self.distro not in ["galactic", "foxy"]:
            include_folders = os.listdir(self.includes)

            for folder in include_folders:
                folder_path = os.path.join(self.includes, folder)
                repeated_path = os.path.join(folder_path, folder)

                if os.path.exists(repeated_path):
                    copy_tree(repeated_path, folder_path)
                    rmtree(repeated_path)

