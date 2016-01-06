# std
import re
from os import path

import logging
import simplejson as json

# project
from utils.dockerutil import get_client as get_docker_client


log = logging.getLogger(__name__)
docker_client = None

PLACEHOLDER_REGEX = re.compile(r'%%.+?%%')


class SDDockerBackend(SDBackend):


def _get_host(container_inspect):
    """Extract the host IP from a docker inspect object."""
    global docker_client
    ip_addr = container_inspect['NetworkSettings']['IPAddress']
    if not ip_addr:
        # kubernetes case
        c_id = container_inspect.get('Id')
        task_id = docker_client.exec_create(c_id, 'hostname -I').get('Id')
        ip_addr = docker_client.exec_start(task_id).strip()
    return ip_addr


def _get_port(container_inspect):
    """Extract the port from a docker inspect object."""
    port = None
    try:
        port = container_inspect['NetworkSettings']['Ports'].keys()[0].split("/")[0]
    except (IndexError, KeyError):
        # kubernetes case
        port = container_inspect['Config']['ExposedPorts'].keys()[0].split("/")[0]
    return port


def _get_explicit_variable(container_inspect, var):
    """Extract the value of a config variable from env variables or docker labels.
       Return None if the variable is not found."""
    conf = _get_config_space(container_inspect['Config'])
    if conf is not None:
        return conf.get(var)


VAR_MAPPING = {
    'host': _get_host,
    'port': _get_port,
}


def _get_template_config(agentConfig, image_name):
    """Extract a template config from a K/V store and returns it as a dict object."""
    # TODO: add more backends
    config_backend = agentConfig.get('sd_config_backend')
    tpl = ConfigStore(config_backend).get_check_tpl(image_name)
    if tpl is not None and len(tpl) == 3 and all(tpl):
        check_name, init_config_tpl, instance_tpl = tpl
    else:
        return None

    try:
        # build a list of all variables to replace in the template
        variables = PLACEHOLDER_REGEX.findall(init_config_tpl) + PLACEHOLDER_REGEX.findall(instance_tpl)
        variables = map(lambda x: x.strip('%'), variables)
        init_config_tpl = json.loads(init_config_tpl)
        instance_tpl = json.loads(instance_tpl)
    except json.JSONDecodeError:
        log.error('Failed to decode the JSON template fetched from {0}.'
                  'Auto-config for {1} failed.'.format(agentConfig.get('sd_backend'), image_name))
        return None
    return [check_name, init_config_tpl, instance_tpl, variables]


def _render_template(init_config_tpl, instance_tpl, variables):
    """Replace placeholders in a template with the proper values.
       Return a list made of `init_config` and `instances`."""
    config = [init_config_tpl, instance_tpl]
    for tpl in config:
        for key in tpl:
            for var in PLACEHOLDER_REGEX.findall(str(tpl[key])):
                if var.strip('%') in variables and variables[var.strip('%')]:
                    tpl[key] = tpl[key].replace(var, variables[var.strip('%')])
                else:
                    log.warning('Failed to find a value for the {0} parameter.'
                                ' The check might not be configured properly.'.format(key))
                    tpl[key].replace(var, '')
    config[1] = config[1]
    return config


def _get_check_config(agentConfig, c_id, image):
    """Retrieve a configuration template and fill it with data pulled from docker."""
    global docker_client
    inspect = docker_client.inspect_container(c_id)
    template_config = _get_template_config(agentConfig, image)
    if template_config is None:
        return None
    check_name, init_config_tpl, instance_tpl, variables = template_config
    var_values = {}
    for v in variables:
        if v in VAR_MAPPING:
            var_values[v] = VAR_MAPPING[v](inspect)
        else:
            var_values[v] = _get_explicit_variable(inspect, v)
    init_config, instances = _render_template(init_config_tpl, instance_tpl, var_values)
    return (check_name, init_config, instances)


def _get_config_space(container_conf):
    """Check whether the user config was provided through env variables or container labels.
       Return this config after removing its `datadog_` prefix."""
    env_variables = {v.split("=")[0].split("datadog_")[1]: v.split("=")[1] for v in container_conf['Env'] if v.split("=")[0].startswith("datadog_")}
    labels = {k.split('datadog_')[1]: v for k, v in container_conf['Labels'].iteritems() if k.startswith("datadog_")}

    if "check_name" in env_variables:
        return env_variables
    elif 'check_name' in labels:
        return labels
    else:
        return None


def get_configs(agentConfig):
    """Get the config for all docker containers running on the host."""
    global docker_client
    docker_client = get_docker_client()
    # TODO: handle containers with the same image (create multiple instances in the check config)
    containers = [(container.get('Image').split(':')[0], container.get('Id'), container.get('Labels')) for container in docker_client.containers()]
    configs = {}

    for image, cid, labels in containers:
        conf = _get_check_config(agentConfig, cid, image)
        if conf is not None:
            check_name = conf[0]
            # build instances list if needed
            if configs.get(check_name) is None:
                configs[check_name] = (conf[1], [conf[2]])
            else:
                if configs[check_name][0] != conf[1]:
                    log.warning('different versions of `init_config` found for check {0}.'
                                ' Keeping the first one found.'.format(check_name))
                configs[check_name][1].append(conf[2])

    return configs
