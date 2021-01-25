#!/usr/bin/python
# Copyright (c) 2020, Sine Nomine Associates
# BSD 2-Clause License

ANSIBLE_METADATA = {
    'metadata_version': '1.1.',
    'status': ['preview'],
    'supported_by': 'community',
}

DOCUMENTATION = r'''
---
module: openafs_wait_for_quorum

short_description: Wait for the dbserver connection and quorom

description:

'''

EXAMPLES = r'''
'''

RETURN = r'''
'''

import json
import logging
import pprint
import re
import time
from ansible.module_utils.basic import AnsibleModule

log = logging.getLogger(__name__)

def main():
    results = dict(
        changed=False,
    )
    module = AnsibleModule(
            argument_spec=dict(
                timeout=dict(type='int', default=600),
                delay=dict(type='int', default=0),
                sleep=dict(type='int', default=20),
                fail_on_timeout=dict(type='bool', default=False)
            ),
            supports_check_mode=False,
    )
    timeout = module.params['timeout']
    delay = module.params['delay']
    sleep = module.params['sleep']
    fail_on_timeout = module.params['fail_on_timeout']
    logfile = '/var/log/ansible-openafs/openafs_wait_for_quorum.log'

    logging.basicConfig(
        level=logging.DEBUG,
        filename=logfile,
        format='%(asctime)s %(levelname)s %(message)s',
    )
    log.info('Starting openafs_wait_for_quorum')
    log.debug('Parameters: %s' % pprint.pformat(module.params))
    if delay < 0:
        log.warning('Ignoring negative delay parameter.')
        delay = 0
    if sleep < 1:
        log.warning('Ignoring out of range sleep parameter.')
        sleep = 1

    def lookup_command(name):
        """
        Lookup an OpenAFS command from local facts file. Try the PATH
        if not found in the local facts.
        """
        try:
            with open('/etc/ansible/facts.d/openafs.fact') as f:
                facts = json.load(f)
            cmd = facts['bins'][name]
        except:
            cmd = module.get_bin_path(name)
        if not cmd:
            module.fail_json(msg='Unable to locate %s command.' % name)
        return cmd

    def check_quorum(port):
        """
        Run udebug to check for quorum.
        """
        status = {'port': port, 'quorum': False}
        udebug = lookup_command('udebug')
        args = [udebug, '-server', 'localhost', '-port', str(port)]
        log.info('Running: %s', ' '.join(args))
        rc, out, err = module.run_command(args)
        log.debug("Ran udebug: rc=%d, out=%s, err=%s", rc, out, err)
        if rc != 0:
            log.warning("Failed udebug: rc=%d, out=%s, err=%s", rc, out, err)
            return status
        status['udebug'] = out
        for line in out.splitlines():
            m = re.match(r'I am sync site', line)
            if m:
                status['sync'] = True
                log.info('Local host is sync site.')
                continue
            m = re.match(r'Recovery state ([0-9a-f]+)', line)
            if m:
                status['flags'] = m.group(1)
                continue
            m = re.match(r'Sync host (\S+) was set \d+ secs ago', line)
            if m:
                if m.group(1) != '0.0.0.0':
                    status['sync_host'] = m.group(1)
                    log.info('Remote host is sync site: %s', status['sync_host'])
                continue
            m = re.match(r"Sync site's db version is (\d+)\.(\d+)", line)
            if m:
                status['db_version'] = (int(m.group(1)), int(m.group(2)))
                continue
        # Check recovery flags if this is the sync site, otherwise check for a
        # remote sync site address.
        if 'sync' in status and status['sync']:
            if 'flags' in status and status['flags'] in ('1f', 'f'):
                status['quorum'] = True
        elif 'sync_host' in status:
            status['quorum'] = True
        return status

    #
    # Wait for PRDB and VLDB quorum.
    #
    if delay:
        time.sleep(delay)
    now = int(time.time())
    expires = now + timeout
    retries = 0
    while True:
        pr = check_quorum(7002)
        vl = check_quorum(7003)
        if pr['quorum'] and vl['quorum']:
            log.info('Databases have quorum.')
            results['pr'] = pr
            results['vl'] = vl
            break
        now = int(time.time())
        if now > expires:
            if fail_on_timeout:
                log.error('Timeout expired.')
                module.fail_json(msg='Timeout expired. See log %s' % logfile)
            else:
                log.warning('Timeout expired.')
                break
        log.info('Will retry in %d seconds.' % sleep)
        time.sleep(sleep)
        retries += 1

    results['retries'] = retries
    log.debug('Results: %s' % pprint.pformat(results))
    log.info('Exiting openafs_wait_for_quorum')
    module.exit_json(**results)

if __name__ == '__main__':
    main()
