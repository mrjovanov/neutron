# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010-2011 OpenStack Foundation
# All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

"""Base Test Case for all Unit Tests"""

import contextlib
import logging
import os
import sys

import eventlet.timeout
import fixtures
import mock
from oslo.config import cfg
import testtools

from neutron.common import constants as const
from neutron import manager
from neutron.openstack.common.notifier import api as notifier_api
from neutron.openstack.common.notifier import test_notifier
from neutron.tests import post_mortem_debug


CONF = cfg.CONF
TRUE_STRING = ['True', '1']
LOG_FORMAT = "%(asctime)s %(levelname)8s [%(name)s] %(message)s"


def fake_use_fatal_exceptions(*args):
    return True


class BaseTestCase(testtools.TestCase):

    def _cleanup_coreplugin(self):
        if manager.NeutronManager._instance:
            agent_notifiers = getattr(manager.NeutronManager._instance.plugin,
                                      'agent_notifiers', {})
            dhcp_agent_notifier = agent_notifiers.get(const.AGENT_TYPE_DHCP)
            if dhcp_agent_notifier:
                dhcp_agent_notifier._plugin = None
        manager.NeutronManager._instance = self._saved_instance

    def setup_coreplugin(self, core_plugin=None):
        self._saved_instance = manager.NeutronManager._instance
        self.addCleanup(self._cleanup_coreplugin)
        manager.NeutronManager._instance = None
        if core_plugin is not None:
            cfg.CONF.set_override('core_plugin', core_plugin)

    def _cleanup_test_notifier(self):
        test_notifier.NOTIFICATIONS = []

    def setup_notification_driver(self, notification_driver=None):
        # to reload the drivers
        self.addCleanup(notifier_api._reset_drivers)
        self.addCleanup(self._cleanup_test_notifier)
        notifier_api._reset_drivers()
        if notification_driver is None:
            notification_driver = [test_notifier.__name__]
        cfg.CONF.set_override("notification_driver", notification_driver)

    def setUp(self):
        super(BaseTestCase, self).setUp()

        # Configure this first to ensure pm debugging support for setUp()
        if os.environ.get('OS_POST_MORTEM_DEBUG') in TRUE_STRING:
            self.addOnException(post_mortem_debug.exception_handler)

        if os.environ.get('OS_DEBUG') in TRUE_STRING:
            _level = logging.DEBUG
        else:
            _level = logging.INFO
        capture_logs = os.environ.get('OS_LOG_CAPTURE') in TRUE_STRING
        if not capture_logs:
            logging.basicConfig(format=LOG_FORMAT, level=_level)
        self.log_fixture = self.useFixture(
            fixtures.FakeLogger(
                format=LOG_FORMAT,
                level=_level,
                nuke_handlers=capture_logs,
            ))

        test_timeout = int(os.environ.get('OS_TEST_TIMEOUT', 0))
        if test_timeout == -1:
            test_timeout = 0
        if test_timeout > 0:
            self.useFixture(fixtures.Timeout(test_timeout, gentle=True))

        # If someone does use tempfile directly, ensure that it's cleaned up
        self.useFixture(fixtures.NestedTempfile())
        self.useFixture(fixtures.TempHomeDir())

        self.addCleanup(mock.patch.stopall)
        self.addCleanup(CONF.reset)

        if os.environ.get('OS_STDOUT_CAPTURE') in TRUE_STRING:
            stdout = self.useFixture(fixtures.StringStream('stdout')).stream
            self.useFixture(fixtures.MonkeyPatch('sys.stdout', stdout))
        if os.environ.get('OS_STDERR_CAPTURE') in TRUE_STRING:
            stderr = self.useFixture(fixtures.StringStream('stderr')).stream
            self.useFixture(fixtures.MonkeyPatch('sys.stderr', stderr))
        self.useFixture(fixtures.MonkeyPatch(
            'neutron.common.exceptions.NeutronException.use_fatal_exceptions',
            fake_use_fatal_exceptions))

        if sys.version_info < (2, 7) and getattr(self, 'fmt', '') == 'xml':
            raise self.skipException('XML Testing Skipped in Py26')

    def config(self, **kw):
        """Override some configuration values.

        The keyword arguments are the names of configuration options to
        override and their values.

        If a group argument is supplied, the overrides are applied to
        the specified configuration option group.

        All overrides are automatically cleared at the end of the current
        test by the fixtures cleanup process.
        """
        group = kw.pop('group', None)
        for k, v in kw.iteritems():
            CONF.set_override(k, v, group)

    @contextlib.contextmanager
    def assert_max_execution_time(self, max_execution_time=5):
        with eventlet.timeout.Timeout(max_execution_time, False):
            yield
            return
        self.fail('Execution of this test timed out')
