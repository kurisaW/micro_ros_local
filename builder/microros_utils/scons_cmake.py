import os
import re
import shutil
from collections.abc import Mapping


_FLAGS_WITH_ARGUMENTS = {'-MF', '-MT', '-MQ', '-MJ', '-o'}
_CONTROL_FLAGS = {'-c', '-S', '-E', '-M', '-MM', '-MD', '-MMD', '-MP', '-MG'}
_SAFE_SHELL_ARGUMENT = re.compile(r'^[A-Za-z0-9_+.,:/=@%-]+$')


def _flatten(value):
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        flattened = []
        for item in value:
            flattened.extend(_flatten(item))
        return flattened
    return [value]


def _unique(values):
    result = []
    seen = set()
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _subst(environment, value):
    value = str(value)
    if hasattr(environment, 'subst'):
        return environment.subst(value)
    return value


def _construction_variable_tokens(environment, variable):
    expression = '${' + variable + '}'
    if hasattr(environment, 'subst_list'):
        return [str(item) for item in _flatten(environment.subst_list(expression)) if str(item)]

    value = environment.get(variable, [])
    return [str(item) for item in _flatten(value) if str(item)]


def _filter_compiler_flags(flags):
    result = []
    skip_next = False

    for flag in flags:
        if skip_next:
            skip_next = False
            continue

        if '$' in flag:
            continue
        if flag in _FLAGS_WITH_ARGUMENTS:
            skip_next = True
            continue
        if flag in _CONTROL_FLAGS:
            continue
        if any(flag.startswith(prefix) for prefix in ('-MF', '-MT', '-MQ', '-MJ', '-o')):
            continue

        result.append(flag)

    return result


def _absolute_include_path(environment, value, base_dir):
    if hasattr(value, 'get_abspath'):
        return os.path.normpath(value.get_abspath())
    if hasattr(value, 'abspath'):
        return os.path.normpath(value.abspath)

    expanded = _subst(environment, value)
    if hasattr(environment, 'Dir'):
        try:
            return os.path.normpath(environment.Dir(expanded).get_abspath())
        except Exception:
            pass

    if expanded.startswith('#'):
        expanded = expanded[1:].lstrip('/\\')
    if not os.path.isabs(expanded):
        expanded = os.path.join(base_dir, expanded)
    return os.path.normpath(os.path.abspath(expanded))


def _definitions(environment, value):
    if value is None:
        return []
    if isinstance(value, Mapping):
        definitions = []
        for name, definition_value in value.items():
            definitions.extend(_definition_pair(environment, name, definition_value))
        return definitions
    if isinstance(value, tuple) and len(value) == 2:
        return _definition_pair(environment, value[0], value[1])

    if not isinstance(value, (str, bytes)):
        try:
            values = iter(value)
        except TypeError:
            values = None

    else:
        values = None

    if values is not None:
        definitions = []
        for item in values:
            definitions.extend(_definitions(environment, item))
        return definitions
    return [_subst(environment, value)]


def _definition_pair(environment, name, value):
    name = _subst(environment, name)
    if value is None:
        return [name]
    return ['{}={}'.format(name, _subst(environment, value))]


def _resolve_tool(environment, variable):
    tool = _subst(environment, '${' + variable + '}').strip()
    if not tool or '$' in tool:
        raise RuntimeError("SCons construction variable {} is not configured".format(variable))

    unquoted_tool = tool.strip('"')
    if os.path.isabs(unquoted_tool) and os.path.isfile(unquoted_tool):
        return os.path.normpath(unquoted_tool)

    if hasattr(environment, 'WhereIs'):
        resolved = environment.WhereIs(unquoted_tool)
        if resolved:
            return os.path.normpath(resolved)

    process_environment = environment.get('ENV', {})
    resolved = shutil.which(unquoted_tool, path=process_environment.get('PATH'))
    return os.path.normpath(resolved) if resolved else unquoted_tool


def collect_scons_build_config(
        environment, base_dir=None, system_processor='aarch64', projects=None):
    if base_dir is None:
        base_dir = os.getcwd()

    include_values = _flatten(environment.get('CPPPATH', []))
    for project in projects or []:
        if isinstance(project, dict):
            include_values.extend(_flatten(project.get('CPPPATH', [])))

    include_paths = [
        _absolute_include_path(environment, path, base_dir)
        for path in include_values
    ]
    include_paths = _unique(include_paths)
    include_flags = [
        '-I' + include_path.replace('\\', '/')
        for include_path in include_paths
    ]

    definitions = _unique(_definitions(environment, environment.get('CPPDEFINES', [])))
    definition_flags = ['-D' + definition for definition in definitions]

    common_flags = _construction_variable_tokens(environment, 'CCFLAGS')
    preprocessor_flags = _construction_variable_tokens(environment, 'CPPFLAGS')
    c_flags = _construction_variable_tokens(environment, 'CFLAGS')
    cxx_flags = _construction_variable_tokens(environment, 'CXXFLAGS')

    c_flags = _filter_compiler_flags(
        c_flags + common_flags + preprocessor_flags + definition_flags + include_flags
    )
    cxx_flags = _filter_compiler_flags(
        cxx_flags + common_flags + preprocessor_flags + definition_flags + include_flags
    )

    return {
        'c_compiler': _resolve_tool(environment, 'CC'),
        'cxx_compiler': _resolve_tool(environment, 'CXX'),
        'archiver': _resolve_tool(environment, 'AR'),
        'system_processor': system_processor,
        'include_paths': include_paths,
        'c_flags': c_flags,
        'cxx_flags': cxx_flags,
    }


def _cmake_quote(value):
    value = str(value).replace('\\', '\\\\')
    value = value.replace(';', '\\;').replace('"', '\\"')
    return '"{}"'.format(value)


def _cmake_path_quote(value):
    return _cmake_quote(str(value).replace('\\', '/'))


def _cmake_bracket_quote(value):
    value = str(value)
    equals = ''
    while ']' + equals + ']' in value:
        equals += '='
    return '[{0}[{1}]{0}]'.format(equals, value)


def _shell_quote(value):
    value = str(value)
    if _SAFE_SHELL_ARGUMENT.match(value):
        return value
    return '"{}"'.format(value.replace('\\', '\\\\').replace('"', '\\"'))


def write_scons_cmake_config(config, path):
    lines = [
        '# Generated from the active RT-Thread SCons environment.',
        'set(RTT_SCONS_C_COMPILER {})'.format(_cmake_path_quote(config['c_compiler'])),
        'set(RTT_SCONS_CXX_COMPILER {})'.format(_cmake_path_quote(config['cxx_compiler'])),
        'set(RTT_SCONS_AR {})'.format(_cmake_path_quote(config['archiver'])),
        'set(RTT_SCONS_SYSTEM_PROCESSOR {})'.format(
            _cmake_quote(config['system_processor'])
        ),
        'set(RTT_SCONS_INCLUDE_DIRS',
    ]

    lines.extend(
        '    {}'.format(_cmake_path_quote(path_value)) for path_value in config['include_paths']
    )
    lines.append(')')
    lines.append(
        'set(RTT_SCONS_C_FLAGS {})'.format(
            _cmake_bracket_quote(' '.join(_shell_quote(flag) for flag in config['c_flags']))
        )
    )
    lines.append(
        'set(RTT_SCONS_CXX_FLAGS {})'.format(
            _cmake_bracket_quote(' '.join(_shell_quote(flag) for flag in config['cxx_flags']))
        )
    )
    lines.append('')

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as config_file:
        config_file.write('\n'.join(lines))
    return os.path.realpath(path)

