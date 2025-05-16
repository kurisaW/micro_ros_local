import os
import sys
import json
import xml.etree.ElementTree as xml_parser
import time
import requests
import geoip2.database

from .utils import run_cmd

def get_country_code():
    try:
        response = requests.get('https://ipinfo.io', timeout=5)
        data = response.json()
        return data['country']
    except Exception as e:
        print(f"Error fetching IP info: {e}")
        return None

class Package:
    def __init__(self, name, path):
        self.name = name
        self.path = path
        self.ignored = False

    def ignore(self):
        self.ignored = True
        ignore_path = self.path + '/COLCON_IGNORE'
        with open(ignore_path, 'a'):
            os.utime(ignore_path, None)

class Repository:
    def __init__(self, name, url, distribution, branch=None):
        self.name = name
        self.url = url
        self.distribution = distribution
        self.branch = distribution if branch is None else branch
        self.path = None

    def clone(self, folder):
        self.path = os.path.join(folder, self.name)
        attempts = 0
        # Download reconnect time, 1s by default
        retry_delay = 1
        # The number of repository redownloads that fail is defined here
        max_attempts = 10

        command = "git clone -b {} {} {}".format(self.branch, self.url, self.path)
        result, stderr = run_cmd(command, capture_output=True)

        if result == 0:
            # Download successfully, exit the loop
            return
        else:
            while attempts < max_attempts:
                attempts += 1
                print("{} clone failed! Retrying...".format(self.name))
                command = "git clone -b {} {} {}".format(self.branch, self.url, self.path)
                result, stderr = run_cmd(command, capture_output=True)
                # Wait a while and try again
                time.sleep(retry_delay)

            # If all attempts fail, print an error message and exit the script
            print("Max attempts reached. Failed to clone {} after {} attempts.".format(self.name, max_attempts))
            sys.exit(1)

    def get_packages(self):
        packages = []
        if os.path.exists(self.path + '/package.xml'):
            packages.append(Package(self.name, self.path))
        else:
            for root, dirs, files in os.walk(self.path):
                path = root.split(os.sep)
                if 'package.xml' in files:
                    package_name = Repository.get_package_name_from_package_xml(os.path.join(root, 'package.xml'))
                    package_path = os.path.join(os.getcwd(), root)
                    packages.append(Package(package_name, package_path))
                elif 'colcon.pkg' in files:
                    package_name = Repository.get_package_name_from_colcon_pkg(os.path.join(root, 'colcon.pkg'))
                    package_path = os.path.join(os.getcwd(), root)
                    packages.append(Package(package_name, package_path))
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
        with open(colcon_pkg, 'r') as f:
            content = json.load(f)
            if content['name']:
                return content['name']
            return None

class Sources:
    country_code = get_country_code()

    if country_code == 'CN':
        micro_ros_mirror_prefix = "https://gitee.com/rtt-microros-mirror"
        print("=========================== Use Chinese mirror source for download ==============================")
    else:
        micro_ros_mirror_prefix = "https://github.com/RT-MicroROS"
        print("=========================== Download using the Github source ==============================")

    dev_environments = {
         'humble': [
            Repository("ament_cmake", micro_ros_mirror_prefix + "/ament_cmake", "humble"),
            Repository("ament_lint", micro_ros_mirror_prefix + "/ament_lint", "humble"),
            Repository("ament_package", micro_ros_mirror_prefix + "/ament_package", "humble"),
            Repository("googletest", micro_ros_mirror_prefix + "/googletest", "humble"),
            Repository("ament_cmake_ros", micro_ros_mirror_prefix +"/ament_cmake_ros", "humble"),
            Repository("ament_index", micro_ros_mirror_prefix + "/ament_index", "humble")
        ],
        'foxy': [
            Repository("ament_cmake", micro_ros_mirror_prefix + "/ament_cmake", "foxy"),
            Repository("ament_lint", micro_ros_mirror_prefix + "/ament_lint", "foxy"),
            Repository("ament_package", micro_ros_mirror_prefix + "/ament_package", "foxy"),
            Repository("googletest", micro_ros_mirror_prefix + "/googletest", "foxy"),
            Repository("ament_cmake_ros", micro_ros_mirror_prefix +"/ament_cmake_ros", "foxy"),
            Repository("ament_index", micro_ros_mirror_prefix + "/ament_index", "foxy")
        ]
    }

    mcu_environments = {
        'humble': [
            Repository("Micro-CDR", micro_ros_mirror_prefix +"/Micro-CDR", "humble", "ros2"),
            Repository("Micro-XRCE-DDS-Client", micro_ros_mirror_prefix +"/Micro-XRCE-DDS-Client", "humble", "ros2"),
            Repository("rcl", micro_ros_mirror_prefix +"/rcl", "humble"),
            Repository("rclc", micro_ros_mirror_prefix +"/rclc", "humble"),
            Repository("micro_ros_utilities", micro_ros_mirror_prefix +"/micro_ros_utilities", "humble"),
            Repository("rcutils", micro_ros_mirror_prefix +"/rcutils", "humble"),
            Repository("micro_ros_msgs", micro_ros_mirror_prefix +"/micro_ros_msgs", "humble"),
            Repository("rmw_microxrcedds", micro_ros_mirror_prefix +"/rmw_microxrcedds", "humble"),
            Repository("rosidl_typesupport", micro_ros_mirror_prefix +"/rosidl_typesupport", "humble"),
            Repository("rosidl_typesupport_microxrcedds", micro_ros_mirror_prefix +"/rosidl_typesupport_microxrcedds", "humble"),
            Repository("rosidl", micro_ros_mirror_prefix +"/rosidl", "humble"),
            Repository("rmw", micro_ros_mirror_prefix +"/rmw", "humble"),
            Repository("rcl_interfaces", micro_ros_mirror_prefix +"/rcl_interfaces", "humble"),
            Repository("rosidl_defaults", micro_ros_mirror_prefix +"/rosidl_defaults", "humble"),
            Repository("unique_identifier_msgs", micro_ros_mirror_prefix +"/unique_identifier_msgs", "humble"),
            Repository("common_interfaces", micro_ros_mirror_prefix +"/common_interfaces", "humble"),
            Repository("test_interface_files", micro_ros_mirror_prefix +"/test_interface_files", "humble"),
            Repository("rmw_implementation", micro_ros_mirror_prefix +"/rmw_implementation", "humble"),
            Repository("rcl_logging", micro_ros_mirror_prefix +"/rcl_logging", "humble"),
            Repository("ros2_tracing", micro_ros_mirror_prefix +"/ros2_tracing", "humble"),
        ],
        'foxy': [   
            Repository("Micro-CDR", micro_ros_mirror_prefix +"/Micro-CDR", "foxy", "ros2"),
            Repository("Micro-XRCE-DDS-Client", "https://gitee.com/kurisaW/Micro-XRCE-DDS-Client", "foxy-bb"),
            Repository("rcl", micro_ros_mirror_prefix +"/rcl", "foxy"),
            Repository("rclc", micro_ros_mirror_prefix +"/rclc", "foxy"),
            Repository("rcutils", micro_ros_mirror_prefix +"/rcutils", "foxy"),
            Repository("micro_ros_msgs", micro_ros_mirror_prefix +"/micro_ros_msgs", "foxy"),
            Repository("rmw_microxrcedds", micro_ros_mirror_prefix +"/rmw_microxrcedds", "foxy"),
            Repository("rosidl_typesupport", micro_ros_mirror_prefix +"/rosidl_typesupport", "foxy"),
            Repository("rosidl_typesupport_microxrcedds", micro_ros_mirror_prefix +"/rosidl_typesupport_microxrcedds", "foxy"),
            Repository("tinydir_vendor", micro_ros_mirror_prefix +"/tinydir_vendor", "foxy", "master"),
            Repository("rosidl", micro_ros_mirror_prefix +"/rosidl", "foxy"),
            Repository("rmw", micro_ros_mirror_prefix +"/rmw", "foxy"),
            Repository("rcl_interfaces", micro_ros_mirror_prefix +"/rcl_interfaces", "foxy"),
            Repository("rosidl_defaults", micro_ros_mirror_prefix +"/rosidl_defaults", "foxy"),
            Repository("unique_identifier_msgs", micro_ros_mirror_prefix +"/unique_identifier_msgs", "foxy"),
            Repository("common_interfaces", micro_ros_mirror_prefix +"/common_interfaces", "foxy"),
            Repository("test_interface_files", micro_ros_mirror_prefix +"/test_interface_files", "foxy"),
            Repository("rmw_implementation", micro_ros_mirror_prefix +"/rmw_implementation", "foxy"),
            Repository("rcl_logging", micro_ros_mirror_prefix +"/rcl_logging", "foxy"),
            Repository("ros2_tracing", "https://gitlab.com/micro-ROS/ros_tracing/ros2_tracing", "foxy", "foxy_microros"),
        ]
    }

    ignore_packages = {
        'humble': ['rcl_logging_log4cxx', 'rcl_logging_spdlog', 'rcl_yaml_param_parser', 'rclc_examples'],
        'foxy': ['rosidl_typesupport_introspection_c', 'rosidl_typesupport_introspection_cpp', 'rcl_logging_log4cxx', 'rcl_logging_spdlog', 'rcl_yaml_param_parser', 'rclc_examples']
    }
