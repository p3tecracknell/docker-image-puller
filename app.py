#! /usr/bin/env python
# -*- coding: utf-8 -*-

import os, sys
import click
import re

from flask import Flask
from flask import request
from flask import jsonify

from docker import Client

DOCKER_HOST = 'unix://var/run/docker.sock'

app = Flask(__name__)
docker = Client(base_url=DOCKER_HOST)

@app.route('/')
def main():
    return jsonify(success=True), 200

@app.route('/images/pull', methods=['POST'])
def image_puller():
    if not request.args['token'] or not request.args['image'] or not request.args['host']:
        return jsonify(success=False, error="Missing parameters"), 400

    if request.args['token'] != os.environ['TOKEN']:
        return jsonify(success=False, error="Invalid token"), 403

    host = request.args['host']
    env = 'VIRTUAL_HOST=' + host
    image = request.args['image']
    image_split = image.split(':')
    image_name = image_split[0]
    image_tag = image_split[1] if len(image_split) == 2 else 'latest'

    old_containers = []
    for cont in docker.containers():
        cont = docker.inspect_container(container=cont['Id'])
        envs = cont['Config']['Env']
        if env in envs:
            old_containers.append(cont)

    print ('Updating', str(len(old_containers)), 'containers with', image, 'image')

    print ('\tPulling new image...')
    docker.pull(image_name, tag=image_tag)
    new_containers = []

    if len(old_containers) is 0:
        print ('\tNo old containers, creating new')
        environment = ['VIRTUAL_HOST=' + host]
        new_cont = docker.create_container(image=image, environment=environment)
        new_containers.append(new_cont)

    print ('\tCreating new containers...')
    for cont in old_containers:
        if 'HOSTNAME' in os.environ and os.environ['HOSTNAME'] == cont['Id']:
            return jsonify(success=False, error="You can't restart the container where the puller script is running"), 403
        new_cont = docker.create_container(image=image, environment=cont['Config']['Env'], host_config=cont['HostConfig'])
        new_containers.append(new_cont)

    print ('\tStopping old containers...')
    for cont in old_containers:
        docker.stop(container=cont['Id'])

    print ('\tStarting new containers...')
    for cont in new_containers:
        print(cont)
        docker.start(container=cont['Id'])

    print ('\tRemoving old containers...')
    for cont in old_containers:
        docker.remove_container(container=cont['Id'])

    return jsonify(success=True), 200

@click.command()
@click.option('-h',      default='0.0.0.0', help='Set the host')
@click.option('-p',      default=8080,      help='Set the listening port')
@click.option('--debug', default=False,     help='Enable debug option')
def main(h, p, debug):
    if not os.environ.get('TOKEN'):
        print ('ERROR: Missing TOKEN env variable')
        sys.exit(1)

    registry_user = os.environ.get('REGISTRY_USER')
    registry_passwd = os.environ.get('REGISTRY_PASSWD')
    registry_url = os.environ.get('REGISTRY_URL', 'https://index.docker.io/v1/')

    if registry_user and registry_passwd:
        try:
            docker.login(username=registry_user, password=registry_passwd, registry=registry_url)
        except Exception as e:
            print(e)
            sys.exit(1)

    app.run(
        host  = os.environ.get('HOST', default=h),
        port  = os.environ.get('PORT', default=p),
        debug = os.environ.get('DEBUG', default=debug)
    )

if __name__ == "__main__":
    main()
