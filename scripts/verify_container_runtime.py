#!/usr/bin/env python3
"""Verify the live PCEP containers against the reviewed isolation contract."""

import argparse
import json
from pathlib import Path
import re
import subprocess


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCKER = '/usr/bin/docker'
DOCKER_HOST = 'unix:///var/run/docker.sock'
BACKEND_CONTAINER = 'pcep_backend'
DATABASE_CONTAINER = 'pcep_db'
BACKEND_IMAGE = 'pcep_webapp-backend:latest'
DATABASE_IMAGE = 'pcep_webapp-postgres:16.15-alpine3.24'
NETWORK = 'pcep_webapp_default'
PROJECT = 'pcep_webapp'
MAX_DOCKER_OUTPUT = 2 * 1024 * 1024
IMAGE_ID_PATTERN = re.compile(r'^sha256:[0-9a-f]{64}$')
CONTAINER_ID_PATTERN = re.compile(r'^[0-9a-f]{64}$')
RELEASE_PATTERN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$')
ENVIRONMENT_NAME_PATTERN = re.compile(r'^[A-Z][A-Z0-9_]*$')
BACKEND_ENVIRONMENT_NAMES = frozenset({
    'CORS_ALLOWED_ORIGINS',
    'DJANGO_ALLOWED_HOSTS',
    'DJANGO_DEBUG',
    'DJANGO_PRODUCTION',
    'DJANGO_SECRET_KEY',
    'GPG_KEY',
    'LANG',
    'PATH',
    'PCEP_RELEASE',
    'PIP_NO_CACHE_DIR',
    'POSTGRES_DB',
    'POSTGRES_HOST',
    'POSTGRES_PASSWORD',
    'POSTGRES_PORT',
    'POSTGRES_USER',
    'PYTHONDONTWRITEBYTECODE',
    'PYTHONUNBUFFERED',
    'PYTHON_SHA256',
    'PYTHON_VERSION',
})
DATABASE_ENVIRONMENT_NAMES = frozenset({
    'DOCKER_PG_LLVM_DEPS',
    'GOSU_VERSION',
    'LANG',
    'PATH',
    'PCEP_APP_DB',
    'PCEP_APP_PASSWORD',
    'PCEP_APP_USER',
    'PGDATA',
    'PG_MAJOR',
    'PG_SHA256',
    'PG_VERSION',
    'POSTGRES_DB',
    'POSTGRES_PASSWORD',
    'POSTGRES_USER',
})
BACKEND_HEALTHCHECK = {
    'Test': [
        'CMD-SHELL',
        "python - <<'PY'\n"
        'import os\n'
        'from urllib.request import Request, urlopen\n'
        "host = os.environ.get('DJANGO_ALLOWED_HOSTS', 'localhost').split(',')[0].strip()\n"
        "req = Request('http://127.0.0.1:8000/api/health/', "
        "headers={'Host': host, 'X-Forwarded-Proto': 'https', "
        "'X-PCEP-Internal-Healthcheck': '1'})\n"
        'with urlopen(req, timeout=3) as response:\n'
        '    raise SystemExit(0 if response.status == 200 else 1)\n'
        'PY',
    ],
    'Interval': 10_000_000_000,
    'Timeout': 5_000_000_000,
    'StartPeriod': 20_000_000_000,
    'Retries': 6,
}
DATABASE_HEALTHCHECK = {
    'Test': [
        'CMD-SHELL',
        'pg_isready -U ${PCEP_APP_USER} -d ${PCEP_APP_DB}',
    ],
    'Interval': 5_000_000_000,
    'Timeout': 5_000_000_000,
    'Retries': 5,
}
REQUIRED_MASKED_PATHS = frozenset({
    '/proc/acpi',
    '/proc/asound',
    '/proc/interrupts',
    '/proc/kcore',
    '/proc/keys',
    '/proc/latency_stats',
    '/proc/sched_debug',
    '/proc/scsi',
    '/proc/timer_list',
    '/proc/timer_stats',
    '/sys/firmware',
})
REQUIRED_READONLY_PATHS = frozenset({
    '/proc/bus',
    '/proc/fs',
    '/proc/irq',
    '/proc/sys',
    '/proc/sysrq-trigger',
})


class ContainerRuntimeError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise ContainerRuntimeError(message)


def docker_command(args):
    try:
        completed = subprocess.run(
            [DOCKER, '--host', DOCKER_HOST, *args],
            cwd=PROJECT_ROOT,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
    except (OSError, UnicodeError, subprocess.SubprocessError) as error:
        raise ContainerRuntimeError('Docker runtime inspection failed.') from error
    if completed.returncode:
        raise ContainerRuntimeError('Docker runtime inspection failed.')
    if len(completed.stdout.encode()) > MAX_DOCKER_OUTPUT:
        raise ContainerRuntimeError('Docker runtime inspection was oversized.')
    return completed.stdout


def json_payload(raw, label):
    try:
        payload = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as error:
        raise ContainerRuntimeError(f'{label} inspection was invalid.') from error
    return payload


def environment_values(entries, expected_names, label):
    require(isinstance(entries, list), f'{label} environment was invalid.')
    values = {}
    for entry in entries:
        require(
            isinstance(entry, str) and '=' in entry,
            f'{label} environment was invalid.',
        )
        name, value = entry.split('=', 1)
        require(
            ENVIRONMENT_NAME_PATTERN.fullmatch(name) is not None,
            f'{label} environment was invalid.',
        )
        values.setdefault(name, []).append(value)
    require(
        frozenset(values) == expected_names,
        f'{label} environment names drifted.',
    )
    require(
        all(len(items) == 1 for items in values.values()),
        f'{label} environment contains duplicate names.',
    )
    return {name: items[0] for name, items in values.items()}


def verify_common(container, service):
    label = f'{service} container'
    image_id = container.get('Image')
    require(
        isinstance(image_id, str)
        and IMAGE_ID_PATTERN.fullmatch(image_id) is not None,
        f'{label} image identity is invalid.',
    )
    state = container.get('State')
    host = container.get('HostConfig')
    config = container.get('Config')
    require(
        isinstance(state, dict)
        and isinstance(host, dict)
        and isinstance(config, dict),
        f'{label} inspection shape is invalid.',
    )
    labels = config.get('Labels')
    require(isinstance(labels, dict), f'{label} labels are invalid.')
    require(
        state.get('Running') is True
        and state.get('Status') == 'running'
        and state.get('Dead') is False
        and state.get('Restarting') is False
        and state.get('OOMKilled') is False
        and isinstance(state.get('Health'), dict)
        and state['Health'].get('Status') == 'healthy',
        f'{label} is not running and healthy.',
    )
    require(labels.get('com.docker.compose.project') == PROJECT,
            f'{label} Compose project label drifted.')
    require(labels.get('com.docker.compose.service') == service,
            f'{label} Compose service label drifted.')
    require(labels.get('com.docker.compose.oneoff') == 'False',
            f'{label} unexpectedly runs as a one-off container.')
    masked_paths = host.get('MaskedPaths')
    readonly_paths = host.get('ReadonlyPaths')
    posture = {
        'read_only': host.get('ReadonlyRootfs') is True,
        'not_privileged': host.get('Privileged') is False,
        'capabilities_dropped': host.get('CapDrop') == ['ALL'],
        'capabilities_not_added': host.get('CapAdd') in (None, []),
        'no_new_privileges': host.get('SecurityOpt')
        == ['no-new-privileges:true'],
        'devices_absent': host.get('Devices') in (None, []),
        'device_requests_absent': host.get('DeviceRequests') in (None, []),
        'legacy_links_absent': host.get('Links') in (None, []),
        'volumes_from_absent': host.get('VolumesFrom') in (None, []),
        'custom_dns_absent': host.get('Dns') in (None, []),
        'dns_options_absent': host.get('DnsOptions') in (None, []),
        'dns_search_absent': host.get('DnsSearch') in (None, []),
        'extra_hosts_absent': host.get('ExtraHosts') in (None, []),
        'private_pid_namespace': host.get('PidMode') == '',
        'private_ipc_namespace': host.get('IpcMode') == 'private',
        'private_uts_namespace': host.get('UTSMode') == '',
        'private_user_namespace_policy': host.get('UsernsMode') == '',
        'private_cgroup_namespace': host.get('CgroupnsMode') == 'private',
        'apparmor_enforced': container.get('AppArmorProfile') == 'docker-default',
        'bounded_processes': host.get('PidsLimit') == 128,
        'bounded_memory': host.get('Memory') == 512 * 1024 * 1024,
        'bounded_memory_swap': host.get('MemorySwap') == 1024 * 1024 * 1024,
        'oom_killer_enabled': host.get('OomKillDisable') is not True,
        'bounded_cpu': host.get('NanoCpus') == 2_000_000_000,
        'sensitive_paths_masked': isinstance(masked_paths, list)
        and set(masked_paths) >= REQUIRED_MASKED_PATHS,
        'sensitive_paths_read_only': isinstance(readonly_paths, list)
        and set(readonly_paths) >= REQUIRED_READONLY_PATHS,
        'reviewed_runtime': host.get('Runtime') == 'runc',
        'publish_all_ports_disabled': host.get('PublishAllPorts') is False,
        'restart_policy': host.get('RestartPolicy')
        == {'Name': 'unless-stopped', 'MaximumRetryCount': 0},
        'rotated_logs': host.get('LogConfig')
        == {'Type': 'json-file', 'Config': {'max-file': '5', 'max-size': '10m'}},
        'reviewed_network': host.get('NetworkMode') == NETWORK,
    }
    failed = sorted(name for name, valid in posture.items() if not valid)
    require(not failed, f'{label} isolation drifted: {", ".join(failed)}.')
    network_settings = container.get('NetworkSettings')
    require(isinstance(network_settings, dict),
            f'{label} network settings are invalid.')
    networks = network_settings.get('Networks')
    require(
        isinstance(networks, dict) and set(networks) == {NETWORK},
        f'{label} network attachment drifted.',
    )
    return host, config


def verify_backend(container, backend_image_id):
    host, config = verify_common(container, 'backend')
    require(
        container['Image'] == backend_image_id,
        'Backend container does not use the reviewed local image.',
    )
    require(config.get('Image') == BACKEND_IMAGE,
            'Backend image reference drifted.')
    require(config.get('User') == 'appuser', 'Backend user drifted.')
    require(config.get('Entrypoint') == ['/app/entrypoint.sh'],
            'Backend entrypoint drifted.')
    require(config.get('Cmd') is None, 'Backend command drifted.')
    require(config.get('WorkingDir') == '/app', 'Backend working directory drifted.')
    require(config.get('StopTimeout') == 45, 'Backend stop timeout drifted.')
    require(config.get('Healthcheck') == BACKEND_HEALTHCHECK,
            'Backend healthcheck drifted.')
    require(host.get('Tmpfs') == {
        '/tmp': 'size=64m,mode=1777,noexec,nosuid,nodev'
    }, 'Backend temporary filesystem drifted.')
    require(host.get('PortBindings') == {
        '8000/tcp': [{'HostIp': '127.0.0.1', 'HostPort': '8001'}]
    }, 'Backend port binding drifted.')
    require(container.get('Mounts') == [], 'Backend mounts drifted.')
    require(host.get('Binds') in (None, []), 'Backend bind mounts drifted.')
    environment = environment_values(
        config.get('Env'), BACKEND_ENVIRONMENT_NAMES, 'Backend'
    )
    expected = {
        'CORS_ALLOWED_ORIGINS': 'https://pcep.micutu.com',
        'DJANGO_ALLOWED_HOSTS': 'pcep.micutu.com,localhost,127.0.0.1',
        'DJANGO_DEBUG': 'False',
        'DJANGO_PRODUCTION': 'True',
        'POSTGRES_DB': 'pcep_db',
        'POSTGRES_HOST': 'db',
        'POSTGRES_PORT': '5432',
        'POSTGRES_USER': 'pcep_user',
    }
    require(
        all(environment.get(name) == value for name, value in expected.items()),
        'Backend production environment drifted.',
    )
    require(environment.get('DJANGO_SECRET_KEY') not in ('', None),
            'Backend Django secret is unavailable.')
    require(environment.get('POSTGRES_PASSWORD') not in ('', None),
            'Backend database credential is unavailable.')
    release = environment.get('PCEP_RELEASE', '')
    require(RELEASE_PATTERN.fullmatch(release) is not None,
            'Backend release metadata is invalid.')
    require(config['Labels'].get('org.opencontainers.image.revision') == release,
            'Backend release label drifted.')
    return release


def verify_database(container):
    host, config = verify_common(container, 'db')
    require(config.get('Image') == DATABASE_IMAGE,
            'Database image reference drifted.')
    require(config.get('User') == 'postgres', 'Database user drifted.')
    require(config.get('Entrypoint') == ['docker-entrypoint.sh'],
            'Database entrypoint drifted.')
    require(config.get('Cmd') == ['postgres'], 'Database command drifted.')
    require(config.get('WorkingDir') == '/', 'Database working directory drifted.')
    require(config.get('StopTimeout') == 60, 'Database stop timeout drifted.')
    require(config.get('StopSignal') == 'SIGINT', 'Database stop signal drifted.')
    require(config.get('Healthcheck') == DATABASE_HEALTHCHECK,
            'Database healthcheck drifted.')
    require(host.get('Tmpfs') == {
        '/tmp': 'size=64m,mode=1777,noexec,nosuid,nodev',
        '/var/run/postgresql': (
            'size=16m,mode=3775,uid=70,gid=70,noexec,nosuid,nodev'
        ),
    }, 'Database temporary filesystems drifted.')
    require(host.get('PortBindings') == {},
            'Database must not publish a host port.')
    require(host.get('Binds') == [
        'pcep_webapp_postgres_data:/var/lib/postgresql/data:rw'
    ], 'Database bind policy drifted.')
    mounts = container.get('Mounts')
    require(isinstance(mounts, list) and len(mounts) == 1,
            'Database mount inventory drifted.')
    mount = mounts[0]
    require(isinstance(mount, dict), 'Database data mount is invalid.')
    require(
        mount.get('Type') == 'volume'
        and mount.get('Name') == 'pcep_webapp_postgres_data'
        and mount.get('Destination') == '/var/lib/postgresql/data'
        and mount.get('RW') is True,
        'Database data mount drifted.',
    )
    environment = environment_values(
        config.get('Env'), DATABASE_ENVIRONMENT_NAMES, 'Database'
    )
    expected = {
        'PCEP_APP_DB': 'pcep_db',
        'PCEP_APP_USER': 'pcep_user',
        'PGDATA': '/var/lib/postgresql/data',
        'PG_MAJOR': '16',
        'POSTGRES_DB': 'pcep_db',
        'POSTGRES_USER': 'pcep_admin',
    }
    require(
        all(environment.get(name) == value for name, value in expected.items()),
        'Database production environment drifted.',
    )
    for name in ('PCEP_APP_PASSWORD', 'POSTGRES_PASSWORD'):
        require(environment.get(name) not in ('', None),
                'Database credential is unavailable.')


def verify_network(network, containers):
    require(network.get('Name') == NETWORK, 'Docker network name drifted.')
    require(network.get('Driver') == 'bridge', 'Docker network driver drifted.')
    require(network.get('Internal') is False,
            'Docker network egress policy drifted.')
    require(network.get('Attachable') is False,
            'Docker network unexpectedly became attachable.')
    require(network.get('Ingress') is False,
            'Docker network unexpectedly became an ingress network.')
    labels = network.get('Labels')
    require(isinstance(labels, dict), 'Docker network labels are invalid.')
    require(labels.get('com.docker.compose.project') == PROJECT,
            'Docker network project label drifted.')
    require(labels.get('com.docker.compose.network') == 'default',
            'Docker network role drifted.')
    members = network.get('Containers')
    require(isinstance(members, dict), 'Docker network members are invalid.')
    require(
        all(isinstance(member, dict) for member in members.values()),
        'Docker network member metadata is invalid.',
    )
    member_names = {member.get('Name') for member in members.values()}
    require(member_names == {BACKEND_CONTAINER, DATABASE_CONTAINER},
            'Docker network membership drifted.')
    expected_ids = {container['Id'] for container in containers.values()}
    require(set(members) == expected_ids,
            'Docker network container identities drifted.')


def verify_container_runtime(runner=None):
    runner = runner or docker_command
    raw_containers = json_payload(
        runner(['inspect', '--type', 'container', BACKEND_CONTAINER, DATABASE_CONTAINER]),
        'Container',
    )
    require(
        isinstance(raw_containers, list) and len(raw_containers) == 2,
        'Container inventory drifted.',
    )
    containers = {}
    for container in raw_containers:
        require(isinstance(container, dict), 'Container inspection shape is invalid.')
        identifier = container.get('Id')
        require(
            isinstance(identifier, str)
            and CONTAINER_ID_PATTERN.fullmatch(identifier) is not None,
            'Container identity is invalid.',
        )
        raw_name = container.get('Name')
        require(isinstance(raw_name, str), 'Container name is invalid.')
        name = raw_name.lstrip('/')
        require(name not in containers, 'Container inventory contains duplicates.')
        containers[name] = container
    require(set(containers) == {BACKEND_CONTAINER, DATABASE_CONTAINER},
            'Container inventory drifted.')

    project_names = {
        line.strip()
        for line in runner([
            'ps', '--all',
            '--filter', f'label=com.docker.compose.project={PROJECT}',
            '--format', '{{.Names}}',
        ]).splitlines()
        if line.strip()
    }
    require(project_names == {BACKEND_CONTAINER, DATABASE_CONTAINER},
            'Unexpected PCEP project container is present.')

    backend_image_id = runner([
        'image', 'inspect', BACKEND_IMAGE, '--format', '{{.Id}}'
    ]).strip()
    require(IMAGE_ID_PATTERN.fullmatch(backend_image_id) is not None,
            'Backend image identity is invalid.')
    release = verify_backend(containers[BACKEND_CONTAINER], backend_image_id)
    verify_database(containers[DATABASE_CONTAINER])

    raw_networks = json_payload(
        runner(['network', 'inspect', NETWORK]), 'Docker network'
    )
    require(
        isinstance(raw_networks, list) and len(raw_networks) == 1
        and isinstance(raw_networks[0], dict),
        'Docker network inspection shape is invalid.',
    )
    verify_network(raw_networks[0], containers)
    return {'containers': 2, 'network_members': 2, 'backend_release': release}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    try:
        result = verify_container_runtime()
    except (ContainerRuntimeError, OSError, ValueError) as error:
        parser.exit(1, f'Container runtime verification failed: {error}\n')
    print(
        'Container runtime verified: '
        f'{result["containers"]} containers, '
        f'{result["network_members"]} network members, '
        f'backend release {result["backend_release"]}.'
    )


if __name__ == '__main__':
    main()
