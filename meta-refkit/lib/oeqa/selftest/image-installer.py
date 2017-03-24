#!/usr/bin/env python
# ex:ts=4:sw=4:sts=4:et
# -*- tab-width: 4; c-basic-offset: 4; indent-tabs-mode: nil -*-
#
# Copyright (c) 2017, Intel Corporation.
# All rights reserved.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#
# AUTHORS
# Patrick Ohly <patrick.ohly@intel.com>
#
# Based on meta/lib/oeqa/selftest/wic.py by Ed Bartosh <ed.bartosh@linux.intel.com>.

"""Test cases for image-installer.bbclass and refkit-installer-image.bb"""

import os

from glob import glob
from shutil import rmtree,copyfile

from oeqa.selftest.base import oeSelfTest
from oeqa.utils.commands import runCmd, bitbake, get_bb_var, get_bb_vars, runqemu
from oeqa.utils.decorators import testcase


class ImageInstaller(oeSelfTest):
    """image-installer.bbclass and refkit-installer-image.bb test class."""

    resultdir = "/var/tmp/image-installer.oe-selftest/"
    image_is_ready = False
    wicenv_cache = {}

    def setUpLocal(self):
        """This code is executed before each test method."""
        self.distro_features = get_bb_var('DISTRO_FEATURES').split()
        self.machine_arch = get_bb_var('MACHINE_ARCH')
        self.image_arch = self.machine_arch.replace('_', '-')
        self.image_dir = get_bb_var('DEPLOY_DIR_IMAGE')

        # Do this here instead of in setUpClass as the base setUp does some
        # clean up which can result in the native tools built earlier in
        # setUpClass being unavailable.
        if not ImageInstaller.image_is_ready:
            bitbake('refkit-installer-image ovmf swtpm-wrappers')
            ImageInstaller.image_is_ready = True

        rmtree(self.resultdir, ignore_errors=True)

    def tearDownLocal(self):
        """Remove resultdir as it may contain images."""
        rmtree(self.resultdir, ignore_errors=True)

    def create_internal_disk(self):
        """Create a internal-image*.wic in the resultdir that runqemu can use."""
        rmtree(self.resultdir, ignore_errors=True)
        bb.utils.mkdirhier(self.resultdir)
        copyfile(os.path.join(self.image_dir, 'refkit-installer-image-%s.qemuboot.conf' % self.image_arch),
                 os.path.join(self.resultdir, 'internal-image-%s.qemuboot.conf' % self.image_arch))
        for ovmf in glob('%s/ovmf*' % self.image_dir):
            os.symlink(ovmf, os.path.join(self.resultdir, os.path.basename(ovmf)))
        with open(os.path.join(self.resultdir, 'internal-image-%s.wic' % self.image_arch), 'w') as f:
            # empty, sparse file of 8GB
            os.truncate(f.fileno(), 8 * 1024 * 1024 * 1024)

    def test_install_no_tpm(self):
        """Test image installation under qemu without virtual TPM"""

        self.create_internal_disk()

        # Install.
        with runqemu('refkit-installer-image', ssh=False,
                     discard_writes=False,
                     qemuparams='-drive if=virtio,file=%s/internal-image-%s.wic,format=raw' % (self.resultdir, self.image_arch),
                     runqemuparams='ovmf',
                     image_fstype='wic') as qemu:
            # Check that we have booted, with dm-verity if enabled.
            cmd = "findmnt / --output SOURCE --noheadings"
            status, output = qemu.run_serial(cmd)
            self.assertEqual(1, status, 'Failed to run command "%s":\n%s' % (cmd, output))
            if 'dm-verity' in self.distro_features:
                self.assertEqual('/dev/mapper/rootfs', output)
            else:
                self.assertIn('vda', output)
            # Now install, non-interactively. Driving the script
            # interactively would be also a worthwhile test...
            cmd = "CHOSEN_INPUT=refkit-image-common-%s.wic CHOSEN_OUTPUT=vdb FORCE=yes image-installer" % self.image_arch
            status, output = qemu.run_serial(cmd, timeout=300)
            self.assertEqual(1, status, 'Failed to run command "%s":\n%s' % (cmd, output))
            bb.note('Installed successfully:\n%s' % output)
            self.assertTrue(output.endswith('Installed refkit-image-common-%s.wic on vdb successfully.' % self.image_arch))

        # Test installation by replacing the normal image with our internal one.
        overrides = {
            'DEPLOY_DIR_IMAGE': self.resultdir,
            'IMAGE_LINK_NAME': 'internal-image-%s' % self.image_arch,
            }
        with runqemu('refkit-installer-image', ssh=False,
                     overrides=overrides,
                     runqemuparams='ovmf',
                     image_fstype='wic') as qemu:
            # Check that we have booted, without device mapper involved.
            # Can't use the simpler findmnt here.
            cmd = "mount"
            status, output = qemu.run_serial(cmd)
            self.assertEqual(1, status, 'Failed to run command "%s":\n%s' % (cmd, output))
            self.assertIn('/dev/vda3 on / ', output)
