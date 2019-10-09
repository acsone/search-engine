# -*- coding: utf-8 -*-
# Copyright 2019 ACSONE SA/NV
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging

from openupgradelib import openupgrade

_logger = logging.getLogger(__name__)


@openupgrade.migrate(use_env=True)
def migrate(env, version):
    _logger.info("Fix cron definition")
    openupgrade.load_data(
        env.cr, "connector_search_engine", "data/ir_cron.xml"
    )
