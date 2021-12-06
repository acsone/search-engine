# -*- coding: utf-8 -*-
# Copyright 2019 ACSONE SA/NV
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging

from odoo import _
from odoo.exceptions import UserError

from odoo.addons.component.core import Component

_logger = logging.getLogger(__name__)

try:
    import elasticsearch
    import elasticsearch.helpers
except ImportError:
    _logger.debug("Can not import elasticsearch")


def _is_delete_nonexistent_documents(elastic_exception):
    """True iff all errors in this exception are deleting a nonexisting document."""
    b = lambda d: "delete" in d and d["delete"]["status"] == 404  # noqa
    return all(b(error) for error in elastic_exception.errors)


class ElasticsearchAdapter(Component):
    _name = "elasticsearch.adapter"
    _inherit = ["se.backend.adapter", "elasticsearch.se.connector"]
    _usage = "se.backend.adapter"

    @property
    def _index_name(self):
        return self.work.index and self.work.index.name.lower()

    def _get_es_client(self):
        backend = self.backend_record

        if backend.es_user or backend.es_password:
            auth = (backend.es_user, backend.es_password)
            es = elasticsearch.Elasticsearch([backend.es_server_host], http_auth=auth)
        else:
            es = elasticsearch.Elasticsearch([backend.es_server_host])

        # TODO: remove, these should not be part of a getter method
        if not es.ping():  # pragma: no cover
            raise ValueError("Connect Exception with elasticsearch")
        self.check_create_missing_index(es, self._index_name)

        return es

    def check_create_missing_index(self, client, index_name):
        """If given an index name, creates it if it does not already exist."""
        if index_name and not client.indices.exists(index_name):
            client.indices.create(
                index=self._index_name, body=self.work.index.config_id.body
            )

    def index(self, datas):
        es = self._get_es_client()
        dataforbulk = []
        for data in datas:
            # Ensure that the _record_id_key is set for creating/updating
            # the record
            if not data.get(self._record_id_key):
                raise UserError(
                    _("The key %s is missing in the data %s")
                    % (self._record_id_key, data)
                )
            else:
                action = {
                    "_index": self._index_name,
                    "_id": data.get(self._record_id_key),
                    "_source": data,
                }
                dataforbulk.append(action)

        res = elasticsearch.helpers.bulk(es, dataforbulk)
        # checks if number of indexed object and object in datas are equal
        return len(datas) - res[0] == 0

    def delete(self, binding_ids):
        es = self._get_es_client()
        records_for_bulk = []
        for binding_id in binding_ids:
            action = {
                "_op_type": "delete",
                "_index": self._index_name,
                "_id": binding_id,
            }
            records_for_bulk.append(action)
        try:
            elasticsearch.helpers.bulk(es, records_for_bulk)
        except elasticsearch.helpers.errors.BulkIndexError as e:
            # if the document we are trying to delete does not exist,
            # we can consider deletion a success (there is nothing to do).
            if not _is_delete_nonexistent_documents(e):
                raise e
            msg = "Trying to delete non-existent documents. Ignored: %s"
            _logger.info(msg, e)

    def clear(self):
        es = self._get_es_client()
        res = es.indices.delete(index=self._index_name, ignore=[400, 404])
        # recreate the index
        self._get_es_client()
        return res["acknowledged"]

    def iter(self):
        # `iter` is a built-in keyword -> to be replaced
        _logger.warning("DEPRECATED: use `each` instead of `iter`.")
        return self.each()

    def each(self):
        es = self._get_es_client()
        res = es.search(index=self._index_name, filter_path=["hits.hits._source"])
        hits = res["hits"]["hits"] if res else []
        return [r["_source"] for r in hits]
