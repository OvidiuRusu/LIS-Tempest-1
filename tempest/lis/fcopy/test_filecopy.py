# Copyright 2014 Cloudbase Solutions Srl
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import time
from tempest import config
from oslo_log import log as logging
from tempest.lis import manager
from tempest.scenario import utils as test_utils
from tempest import test

CONF = config.CONF

LOG = logging.getLogger(__name__)


class FileCopy(manager.LisBase):

    def setUp(self):
        super(FileCopy, self).setUp()
        # Setup image and flavor the test instance
        # Support both configured and injected values
        if not hasattr(self, 'image_ref'):
            self.image_ref = CONF.compute.image_ref
        if not hasattr(self, 'flavor_ref'):
            self.flavor_ref = CONF.compute.flavor_ref
        self.image_utils = test_utils.ImageUtils(self.manager)
        if not self.image_utils.is_flavor_enough(self.flavor_ref,
                                                 self.image_ref):
            raise self.skipException(
                '{image} does not fit in {flavor}'.format(
                    image=self.image_ref, flavor=self.flavor_ref
                )
            )
        self.host_name = ""
        self.instance_name = ""
        self.test_file = ""
        self.file_path = ""
        self.run_ssh = CONF.validation.run_validation and \
            self.image_utils.is_sshable_image(self.image_ref)
        self.ssh_user = CONF.validation.image_ssh_user
        LOG.debug('Starting test for i:{image}, f:{flavor}. '
                  'Run ssh: {ssh}, user: {ssh_user}'.format(
                      image=self.image_ref, flavor=self.flavor_ref,
                      ssh=self.run_ssh, ssh_user=self.ssh_user))

    def _create_test_file(self, size):
        vhd_path = self.default_vhd_path()
        vhd_path = vhd_path.rstrip()
        vhd_path = vhd_path + "\\"
        self.test_file = "testfile-" + time.strftime("%d-%m-%Y-%H-%M-%S") + ".file"
        self.file_path = vhd_path + self.test_file
        if size.endswith('MB'):
            size = size.replace('MB', '')
            size = long(size)
            size = size * 1024 * 1024
        elif size.endswith('GB'):
            size = size.replace('GB', '')
            size = long(size)
            size = size * 1024 * 1024 * 1024
        else:
            size = long(size)

        cmd = "fsutil file createnew '{file_path}' {size}".format(
            file_path=self.file_path, size=size)
        out = self.host_client.run_powershell_cmd(cmd)
        if "is created" not in out:
            raise Exception("ERROR: Could not create file " + self.file_path)

        return size

    @test.attr(type=['smoke', 'core', 'filecopy', 'guest'])
    @test.services('compute', 'network')
    def test_fcopy_basic(self):
        self.spawn_vm()
        self._initiate_linux_client(
            self.floating_ip['floatingip']['floating_ip_address'],
            self.ssh_user, self.keypair['private_key'])

        # Verify if Guest Service is enabled. If not, we enable it
        status = self.verify_lis(self.instance_name, "'Guest Service Interface'")
        if status == 'false':
            self.stop_vm(self.server_id)
            self.enable_lis(self.instance_name, "'Guest Service Interface'")
            self.start_vm(self.server_id)
            self._initiate_linux_client(
                self.floating_ip['floatingip']['floating_ip_address'],
                self.ssh_user, self.keypair['private_key'])

        self.verify_lis_status(self.instance_name, "'Guest Service Interface'")
        self.linux_client.verify_daemon("'[h]v_fcopy_daemon\|[h]ypervfcopyd'")
        size = '10MB'
        test_size = self._create_test_file(size)

        out, error, code = self.copy_vmfile(self.instance_name, self.file_path)
        if code != 0:
            self.remove_file(self.file_path)
            raise Exception(
                "ERROR: Couldn't copy the file: " + error + ', ' + code)

        file_size = self.linux_client.check_file_size('/tmp/' + self.test_file)
        if file_size != test_size:
            self.remove_file(self.file_path)
            raise Exception("ERROR: The file doesn't match the 10MB size!")
        self.remove_file(self.file_path)
        self.servers_client.delete_server(self.instance['id'])

    @test.attr(type=['smoke', 'core', 'filecopy', 'guest', 'exists'])
    @test.services('compute', 'network')
    def test_fcopy_file_exists_overwrite(self):
        self.spawn_vm()
        self._initiate_linux_client(
            self.floating_ip['floatingip']['floating_ip_address'],
            self.ssh_user, self.keypair['private_key'])

        # Verify if Guest Service is enabled. If not, we enable it
        status = self.verify_lis(self.instance_name, "'Guest Service Interface'")
        if status == 'false':
            self.stop_vm(self.server_id)
            self.enable_lis(self.instance_name, "'Guest Service Interface'")
            self.start_vm(self.server_id)
            self._initiate_linux_client(
                self.floating_ip['floatingip']['floating_ip_address'],
                self.ssh_user, self.keypair['private_key'])

        self.verify_lis_status(self.instance_name, "'Guest Service Interface'")
        self.linux_client.verify_daemon("'[h]v_fcopy_daemon\|[h]ypervfcopyd'")
        size = '10MB'
        test_size = self._create_test_file(size)

        out, error, code = self.copy_vmfile(self.instance_name, self.file_path)
        if code != 0:
            self.remove_file(self.file_path)
            raise Exception(
                "ERROR: Couldn't copy the file: " + error + ', ' + code)
        file_size = self.linux_client.check_file_size('/tmp/' + self.test_file)
        if file_size != test_size:
            self.remove_file(self.file_path)
            raise Exception("ERROR: The file doesn't match the 10MB size!")

        out, error, code = self.copy_vmfile(self.instance_name, self.file_path)
        if code != 1:
            self.remove_file(self.file_path)
            raise Exception(
                "ERROR: Could copy the file: " + error + ', ' + code)

        out, error, code = self.copy_vmfile(
            self.instance_name, self.file_path, overwrite=True)
        if code != 0:
            self.remove_file(self.file_path)
            raise Exception(
                "ERROR: Couldn't overwrite the file: " + error + ', ' + code)

        self.remove_file(self.file_path)
        self.servers_client.delete_server(self.instance['id'])
