import configparser
import re

import click

from .utils import construct_table, run_group_command


@click.group()
@click.option(
    '-h',
    '--hosts',
    type=click.STRING,
    help='Run command on specified hosts (default all).'
)
@click.pass_context
def cli(ctx, hosts):
    """Tools aimed at making work in the Sinzlab easier."""
    config = configparser.ConfigParser()
    config.read('config.ini')
    if hosts:
        hosts = hosts.split(',')
    else:
        hosts = config['DEFAULT']['hosts'].split()
    common = config['DEFAULT']['common']
    ctx.ensure_object(dict)
    ctx.obj['hosts'] = ['.'.join([h, common]) for h in hosts]
    ctx.obj['user'] = config['DEFAULT']['user']


@cli.command()
@click.pass_context
def check_gpus(ctx):
    """Get monitoring information for GPUs."""
    command = (
        'nvidia-smi '
        + '--format=csv,noheader,nounits '
        + '--query-gpu=' + (
            'index,'
            + 'utilization.gpu,'
            + 'temperature.gpu,'
            + 'memory.used,'
            + 'memory.total'
        )
    )
    field_names = (
        'INDEX',
        'UTIL (%)',
        'TEMP (°C)',
        'USED (MiB)',
        'TOTAL (MiB)'
    )
    results = run_group_command(ctx.obj['hosts'], ctx.obj['user'], command)
    data = {}
    for connection, result in sorted(results.items()):
        result = [l.split(', ') for l in result.stdout.split('\n')][:-1]
        gpus = []
        for line in result:
            gpus.append({k: v for k, v in zip(field_names, line)})
        data[connection] = gpus
    click.echo(construct_table(field_names, data))


@cli.group()
@click.pass_context
def docker(_):
    """Docker commands."""
    pass


@docker.command()
@click.option(
    '-a',
    '--all',
    'all_containers',
    is_flag=True,
    help='Show all containers (default shows just running).'
)
@click.option(
    '-f',
    '--filter',
    'container_filters',
    type=click.STRING,
    multiple=True,
    help='Filter output based on conditions provided.'
)
@click.option(
    '-n',
    '--last',
    'n_last_containers',
    type=click.INT,
    help='Show n last created containers (includes all states) (default -1).'
)
@click.option(
    '-l',
    '--latest',
    'latest_container',
    is_flag=True,
    help='Show the latest created container (includes all states).'
)
@click.pass_context
def ps(
        ctx,
        all_containers,
        container_filters,
        n_last_containers,
        latest_container
):
    """List containers."""
    # Assemble docker ps command
    field_names = [
        'ID',
        'Image',
        'Command',
        'RunningFor',
        'Status',
        'Ports',
        'Names',
    ]
    go_template = ', '.join(['{{.' + k + '}}' for k in field_names])
    command = [f'docker ps --format "{go_template}"']
    if all_containers:
        command.append('--all')
    for container_filter in container_filters:
        command.append(f'--filter {container_filter}')
    if n_last_containers:
        command.append(f'--last {n_last_containers}')
    if latest_container:
        command.append('--latest')
    command = ' '.join(command)
    # Run command
    results = run_group_command(ctx.obj['hosts'], ctx.obj['user'], command)
    # Parse results
    data = {}
    for connection, result in results.items():
        lines = result.stdout.split('\n')[:-1]
        if lines:
            containers = []
            for line in lines:
                values = line.split(', ')
                con_id = values[0]
                container = {k: v for k, v in zip(field_names, values)}
                result = connection.run(
                    'docker inspect --format "{{.Config.Env}}" ' + con_id,
                    hide=True
                )
                match = re.search(
                    r'NVIDIA_VISIBLE_DEVICES=(all|\d+)', result.stdout)
                container['GPU'] = match.group(1) if match else ''
                containers.append(container)
        else:
            containers = []
        data[connection] = containers
    # Print result as table
    click.echo(construct_table(field_names + ['GPU'], data))


@docker.command()
@click.option(
    '-u',
    '--username',
    type=click.STRING,
    prompt=True,
    help='Username.'
)
@click.option(
    '-p',
    '--password',
    type=click.STRING,
    prompt=True,
    hide_input=True,
    help='Password.'
)
@click.pass_context
def login(ctx, username, password):
    """Log in to a Docker registry."""
    command = f'docker login -u {username} -p {password}'
    run_group_command(ctx.obj['hosts'], ctx.obj['user'], command)


@docker.command(context_settings=dict(
    ignore_unknown_options=True,
    allow_extra_args=True
))
@click.argument('image')
@click.pass_context
def pull(ctx, image):
    """Pull an image or a repository from a registry."""
    command = ' '.join([f'docker pull {image}'] + ctx.args)
    run_group_command(ctx.obj['hosts'], ctx.obj['user'], command)


if __name__ == '__main__':
    cli()
