# Copyright 2020 Camptocamp SA (http://www.camptocamp.com).
# @author Simone Orsi <simahawk@gmail.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
import logging

from odoo import SUPERUSER_ID, api
from odoo.tools.sql import set_not_null

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for backend in env["se.backend.algolia"].search([("tech_name", "=", False)]):
        backend._onchange_name_for_tech()
        _logger.info(
            "Backend '%s' `tech_name` set automatically. "
            "Please check if it suits your env.",
            backend.name,
        )
        backend.flush()
    set_not_null(cr, "se_backend_algolia", "tech_name")
