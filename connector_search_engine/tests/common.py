# -*- coding: utf-8 -*-
# Copyright 2018 Simone Orsi - Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from contextlib import contextmanager

import mock
import urlparse
from openerp import tools
from openerp.addons.component.tests.common import SavepointComponentCase
from openerp.addons.connector.tests.common import mock_job_delay_to_direct
from openerp.modules.module import get_resource_path


def load_xml(env, module, filepath):
    with mock.patch.object(env.cr.__class__, "commit"):
        tools.convert_file(
            env.cr,
            module,
            get_resource_path(module, filepath),
            {},
            mode="init",
            noupdate=False,
            kind="test",
        )


@contextmanager
def mock_job_delays():
    with mock_job_delay_to_direct(
        "openerp.addons.connector_search_engine.models."
        "se_binding.se_binding_do_synchronize"
    ), mock_job_delay_to_direct(
        "openerp.addons.connector_search_engine.models."
        "se_binding.se_binding_do_recompute_json"
    ), mock_job_delay_to_direct(
        "openerp.addons.connector_search_engine.models."
        "se_index.se_index_do_delete_obsolete_item"
    ), mock_job_delay_to_direct(
        "openerp.addons.connector_search_engine.models."
        "se_index.se_index_do_batch_export"
    ):
        yield


class TestSeBackendCaseBase(SavepointComponentCase):
    @classmethod
    def setUpClass(cls):
        super(TestSeBackendCaseBase, cls).setUpClass()
        cls.env = cls.env(
            context=dict(
                cls.env.context,
                tracking_disable=True,  # speed up tests
                # TODO: requires https://github.com/OCA/queue/pull/114
                test_queue_job_no_delay=True,  # no jobs thanks
            )
        )
        cls.se_index_model = cls.env["se.index"]

    @classmethod
    def _load_fixture(cls, fixture, module="connector_search_engine"):
        load_xml(cls.env, module, "tests/fixtures/%s" % fixture)

    @staticmethod
    def parse_path(url):
        return urlparse.urlparse(url).path

    def run(self, *args, **kwargs):
        with mock_job_delays():
            return super(TestSeBackendCaseBase, self).run(*args, **kwargs)
