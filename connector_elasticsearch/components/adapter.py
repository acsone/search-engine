# -*- coding: utf-8 -*-
# Copyright 2019 ACSONE SA/NV
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging
import time

from odoo import exceptions

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

    def _get_current_aliased_index_name(self, client):
        current_aliased_index_name = None
        alias = client.indices.get_alias(name=self._index_name, ignore=[400, 404])
        if "error" not in alias:
            current_aliased_index_name = alias.keys()[0]
        return current_aliased_index_name

    def _get_next_aliased_index_name(self, aliased_index_name=None):
        next_version = 1
        if aliased_index_name:
            next_version = int(aliased_index_name.split("-")[-1]) + 1
        return "%s-%d" % (self._index_name, next_version)

    def check_create_missing_index(self, client, index_name):
        """If given an index name, creates it if it does not already exist."""
        if index_name and not client.indices.exists(index_name):
            # To allow rolling updates, we work with index aliases
            aliased_index_name = self._get_next_aliased_index_name()
            client.indices.create(
                index=aliased_index_name, body=self.work.index.config_id.body
            )
            client.indices.put_alias(index=aliased_index_name, name=self._index_name)

    def index(self, records):
        es = self._get_es_client()
        records_for_bulk = []
        for record in records:
            error = self._validate_record(record)
            if error:
                raise exceptions.ValidationError(error)
            action = {
                "_index": self._index_name,
                "_id": record.get(self._record_id_key),
                "_source": record,
            }
            records_for_bulk.append(action)

        res = elasticsearch.helpers.bulk(es, records_for_bulk)
        # checks if number of indexed object and object in records are equal
        return len(records) - res[0] == 0

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
        client = self._get_es_client()
        current_aliased_index_name = self._get_current_aliased_index_name(client=client)
        next_aliased_index_name = self._get_next_aliased_index_name(current_aliased_index_name)
        # create new idx
        client.indices.create(
            index=next_aliased_index_name, body=self.work.index.config_id.body
        )
        task_def = client.reindex(
            {
                "source": {"index": self._index_name},
                "dest": {"index": next_aliased_index_name},
            },
            request_timeout=9999999,
            wait_for_completion=False
        )
        while True:
            # TODO should be done into a job but not possible
            # with component :-( (an other motivation to drop component)
            time.sleep(5)
            _logger.info("Waiting for task completion %", task_def)
            task = client.tasks.get(task_id=task_def["task"], wait_for_completion=False)
            if task.get('completed'):
                break
        if current_aliased_index_name:
            client.indices.update_aliases(body={
                "actions": [
                    {
                        "remove": {
                            "index": current_aliased_index_name,
                            "alias": self._index_name
                        },
                    }, {
                        "add": {
                            "index": next_aliased_index_name,
                            "alias": self._index_name
                        }
                    }
                ]
            })
            client.indices.delete(index=current_aliased_index_name, ignore=[400, 404])
        else:
            # This code will only be triggered the first time the reindex is
            # called on an index created before the use of index aliases.
            client.indices.delete(index=idx_name,
                                  ignore=[400, 404])
            client.indices.put_alias(index=next_aliased_index_name,
                                     name=idx_name)
