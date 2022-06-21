# -*- coding: utf-8 -*-
# Copyright 2019 ACSONE SA/NV
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class SeIndex(models.Model):

    _inherit = "se.index"

    config_id = fields.Many2one(
        comodel_name="se.index.config",
        string="Config",
        help="Elasticseacrh index definition (see https://www.elastic.co/"
        "guide/en/elasticsearch/reference/current/"
        "indices-create-index.html)",
    )

    @api.constrains("config_id", "backend_id")
    def _check_config_id_required(self):
        for rec in self:
            if (
                rec.backend_id.specific_model == "se.backend.elasticsearch"
                and not rec.config_id
            ):
                raise ValidationError(
                    _("An index definition is rquired for elasticsearch")
                )

    def reindex(self):
        """Reindex records according to the current config

        This method is useful to allows a rolling update of index
        configuration.

        This process is based on the following steps:
        1. create a new index with the current config
        2. trigger a reindex into SE from the current index to the new one
        3. Update the index alias to point to the new index
        4. Drop the old index.
        """
        self.ensure_one()
        adapter = self._get_backend_adapter()
        adapter.reindex()
        return True
