import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


spec = importlib.util.spec_from_file_location(
    'verify_container_runtime',
    Path(__file__).resolve().parents[3] / 'scripts/verify_container_runtime.py',
)
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)

BACKEND_ID = 'a' * 64
DATABASE_ID = 'b' * 64
BACKEND_IMAGE_ID = f'sha256:{"c" * 64}'
DATABASE_IMAGE_ID = f'sha256:{"d" * 64}'


def environment(names, overrides):
    return [f'{name}={overrides.get(name, "value")}' for name in sorted(names)]


def common_container(identifier, name, service, image):
    return {
        'Id': identifier,
        'Name': f'/{name}',
        'Image': image,
        'AppArmorProfile': 'docker-default',
        'State': {
            'Running': True,
            'Status': 'running',
            'Dead': False,
            'Restarting': False,
            'OOMKilled': False,
            'Health': {'Status': 'healthy'},
        },
        'Config': {
            'Labels': {
                'com.docker.compose.project': runtime.PROJECT,
                'com.docker.compose.service': service,
                'com.docker.compose.oneoff': 'False',
            },
        },
        'HostConfig': {
            'ReadonlyRootfs': True,
            'Privileged': False,
            'CapDrop': ['ALL'],
            'CapAdd': None,
            'SecurityOpt': ['no-new-privileges:true'],
            'Devices': None,
            'DeviceRequests': None,
            'Links': None,
            'VolumesFrom': None,
            'Dns': None,
            'DnsOptions': None,
            'DnsSearch': None,
            'ExtraHosts': [],
            'PidMode': '',
            'IpcMode': 'private',
            'UTSMode': '',
            'UsernsMode': '',
            'CgroupnsMode': 'private',
            'PidsLimit': 128,
            'Memory': 512 * 1024 * 1024,
            'MemorySwap': 1024 * 1024 * 1024,
            'OomKillDisable': None,
            'NanoCpus': 2_000_000_000,
            'MaskedPaths': sorted(runtime.REQUIRED_MASKED_PATHS),
            'ReadonlyPaths': sorted(runtime.REQUIRED_READONLY_PATHS),
            'Runtime': 'runc',
            'PublishAllPorts': False,
            'RestartPolicy': {
                'Name': 'unless-stopped',
                'MaximumRetryCount': 0,
            },
            'LogConfig': {
                'Type': 'json-file',
                'Config': {'max-file': '5', 'max-size': '10m'},
            },
            'NetworkMode': runtime.NETWORK,
        },
        'NetworkSettings': {'Networks': {runtime.NETWORK: {}}},
    }


def reviewed_runtime():
    backend = common_container(
        BACKEND_ID,
        runtime.BACKEND_CONTAINER,
        'backend',
        BACKEND_IMAGE_ID,
    )
    backend['Config'].update({
        'Image': runtime.BACKEND_IMAGE,
        'User': 'appuser',
        'Entrypoint': ['/app/entrypoint.sh'],
        'Cmd': None,
        'WorkingDir': '/app',
        'StopTimeout': 45,
        'Healthcheck': copy.deepcopy(runtime.BACKEND_HEALTHCHECK),
        'Env': environment(
            runtime.BACKEND_ENVIRONMENT_NAMES,
            {
                'CORS_ALLOWED_ORIGINS': 'https://pcep.micutu.com',
                'DJANGO_ALLOWED_HOSTS': (
                    'pcep.micutu.com,localhost,127.0.0.1'
                ),
                'DJANGO_DEBUG': 'False',
                'DJANGO_PRODUCTION': 'True',
                'DJANGO_SECRET_KEY': 'private-value',
                'PCEP_RELEASE': 'abcdef123456',
                'POSTGRES_DB': 'pcep_db',
                'POSTGRES_HOST': 'db',
                'POSTGRES_PASSWORD': 'private-value',
                'POSTGRES_PORT': '5432',
                'POSTGRES_USER': 'pcep_user',
            },
        ),
    })
    backend['Config']['Labels']['org.opencontainers.image.revision'] = (
        'abcdef123456'
    )
    backend['HostConfig'].update({
        'Tmpfs': {'/tmp': 'size=64m,mode=1777,noexec,nosuid,nodev'},
        'PortBindings': {
            '8000/tcp': [{'HostIp': '127.0.0.1', 'HostPort': '8001'}]
        },
        'Binds': None,
    })
    backend['Mounts'] = []

    database = common_container(
        DATABASE_ID,
        runtime.DATABASE_CONTAINER,
        'db',
        DATABASE_IMAGE_ID,
    )
    database['Config'].update({
        'Image': runtime.DATABASE_IMAGE,
        'User': 'postgres',
        'Entrypoint': ['docker-entrypoint.sh'],
        'Cmd': ['postgres'],
        'WorkingDir': '/',
        'StopTimeout': 60,
        'StopSignal': 'SIGINT',
        'Healthcheck': copy.deepcopy(runtime.DATABASE_HEALTHCHECK),
        'Env': environment(
            runtime.DATABASE_ENVIRONMENT_NAMES,
            {
                'PCEP_APP_DB': 'pcep_db',
                'PCEP_APP_PASSWORD': 'private-value',
                'PCEP_APP_USER': 'pcep_user',
                'PGDATA': '/var/lib/postgresql/data',
                'PG_MAJOR': '16',
                'POSTGRES_DB': 'pcep_db',
                'POSTGRES_PASSWORD': 'private-value',
                'POSTGRES_USER': 'pcep_admin',
            },
        ),
    })
    database['HostConfig'].update({
        'Tmpfs': {
            '/tmp': 'size=64m,mode=1777,noexec,nosuid,nodev',
            '/var/run/postgresql': (
                'size=16m,mode=3775,uid=70,gid=70,noexec,nosuid,nodev'
            ),
        },
        'PortBindings': {},
        'Binds': [
            'pcep_webapp_postgres_data:/var/lib/postgresql/data:rw'
        ],
    })
    database['Mounts'] = [{
        'Type': 'volume',
        'Name': 'pcep_webapp_postgres_data',
        'Destination': '/var/lib/postgresql/data',
        'RW': True,
    }]
    network = {
        'Name': runtime.NETWORK,
        'Driver': 'bridge',
        'Internal': False,
        'Attachable': False,
        'Ingress': False,
        'Labels': {
            'com.docker.compose.project': runtime.PROJECT,
            'com.docker.compose.network': 'default',
        },
        'Containers': {
            BACKEND_ID: {'Name': runtime.BACKEND_CONTAINER},
            DATABASE_ID: {'Name': runtime.DATABASE_CONTAINER},
        },
    }
    return {'backend': backend, 'database': database, 'network': network}


def runner_for(payload, project_names=None):
    responses = {
        (
            'inspect', '--type', 'container',
            runtime.BACKEND_CONTAINER, runtime.DATABASE_CONTAINER,
        ): json.dumps([payload['backend'], payload['database']]),
        (
            'ps', '--all', '--filter',
            f'label=com.docker.compose.project={runtime.PROJECT}',
            '--format', '{{.Names}}',
        ): '\n'.join(
            project_names
            or [runtime.BACKEND_CONTAINER, runtime.DATABASE_CONTAINER]
        ),
        (
            'image', 'inspect', runtime.BACKEND_IMAGE,
            '--format', '{{.Id}}',
        ): BACKEND_IMAGE_ID,
        ('network', 'inspect', runtime.NETWORK): json.dumps([payload['network']]),
    }

    def run(args):
        return responses[tuple(args)]

    return run


def verify(payload, project_names=None):
    return runtime.verify_container_runtime(
        runner=runner_for(payload, project_names=project_names)
    )


def test_accepts_exact_hardened_runtime_and_topology():
    assert verify(reviewed_runtime()) == {
        'containers': 2,
        'network_members': 2,
        'backend_release': 'abcdef123456',
    }


@pytest.mark.parametrize(
    'field,value,failed_check',
    [
        ('Privileged', True, 'not_privileged'),
        ('NanoCpus', 0, 'bounded_cpu'),
        ('CapAdd', ['SYS_ADMIN'], 'capabilities_not_added'),
        ('NetworkMode', 'host', 'reviewed_network'),
        ('ExtraHosts', ['db:203.0.113.10'], 'extra_hosts_absent'),
        ('MemorySwap', -1, 'bounded_memory_swap'),
        ('MaskedPaths', [], 'sensitive_paths_masked'),
    ],
)
def test_rejects_backend_isolation_drift(field, value, failed_check):
    payload = reviewed_runtime()
    payload['backend']['HostConfig'][field] = value

    with pytest.raises(runtime.ContainerRuntimeError, match=failed_check):
        verify(payload)


def test_rejects_public_backend_port_or_persistent_mount():
    payload = reviewed_runtime()
    payload['backend']['HostConfig']['PortBindings']['8000/tcp'][0][
        'HostIp'
    ] = '0.0.0.0'
    with pytest.raises(runtime.ContainerRuntimeError, match='port binding'):
        verify(payload)

    payload = reviewed_runtime()
    payload['backend']['Mounts'] = [{
        'Type': 'bind', 'Destination': '/app', 'RW': True
    }]
    with pytest.raises(runtime.ContainerRuntimeError, match='mounts'):
        verify(payload)


def test_rejects_backend_environment_or_release_label_drift():
    payload = reviewed_runtime()
    payload['backend']['Config']['Env'].append(
        'POSTGRES_ADMIN_PASSWORD=SENSITIVE_VALUE'
    )
    with pytest.raises(runtime.ContainerRuntimeError, match='names drifted') as error:
        verify(payload)
    assert 'SENSITIVE_VALUE' not in str(error.value)

    payload = reviewed_runtime()
    payload['backend']['Config']['Labels'][
        'org.opencontainers.image.revision'
    ] = 'other-release'
    with pytest.raises(runtime.ContainerRuntimeError, match='release label'):
        verify(payload)


def test_rejects_database_port_mount_or_admin_identity_drift():
    payload = reviewed_runtime()
    payload['database']['HostConfig']['PortBindings'] = {
        '5432/tcp': [{'HostIp': '0.0.0.0', 'HostPort': '5432'}]
    }
    with pytest.raises(runtime.ContainerRuntimeError, match='host port'):
        verify(payload)

    payload = reviewed_runtime()
    payload['database']['Mounts'][0]['Name'] = 'unreviewed-volume'
    with pytest.raises(runtime.ContainerRuntimeError, match='data mount'):
        verify(payload)

    payload = reviewed_runtime()
    payload['database']['Config']['User'] = 'root'
    with pytest.raises(runtime.ContainerRuntimeError, match='user'):
        verify(payload)


def test_rejects_unexpected_project_container_or_network_peer():
    payload = reviewed_runtime()
    with pytest.raises(runtime.ContainerRuntimeError, match='project container'):
        verify(
            payload,
            project_names=[
                runtime.BACKEND_CONTAINER,
                runtime.DATABASE_CONTAINER,
                'pcep_rogue',
            ],
        )

    payload = reviewed_runtime()
    payload['network']['Containers']['rogue-id'] = {'Name': 'unreviewed'}
    with pytest.raises(runtime.ContainerRuntimeError, match='membership'):
        verify(payload)


def test_docker_failure_does_not_echo_stderr(monkeypatch):
    monkeypatch.setattr(
        runtime.subprocess,
        'run',
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=1,
            stdout='',
            stderr='SENSITIVE_DOCKER_DETAIL',
        ),
    )

    with pytest.raises(runtime.ContainerRuntimeError) as error:
        runtime.docker_command(['inspect', runtime.BACKEND_CONTAINER])

    assert str(error.value) == 'Docker runtime inspection failed.'
    assert 'SENSITIVE_DOCKER_DETAIL' not in str(error.value)
