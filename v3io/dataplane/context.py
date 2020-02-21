import os

import future.utils
import requests

import v3io.common.helpers
import v3io.dataplane.session
import v3io.dataplane.response
import v3io.dataplane.output
import v3io.dataplane.input
import v3io.dataplane.items_cursor


class Context(object):

    def __init__(self, logger, endpoints=None, max_connections=4, timeout=None):
        self._logger = logger
        self._endpoints = self._get_endpoints(endpoints)
        self._next_connection_pool = 0
        self._timeout = timeout

        # create a tuple of connection pools
        self._connection_pools = self._create_connection_pools(self._endpoints, max_connections)

    def new_items_cursor(self, container_name, access_key, **kwargs):
        return v3io.dataplane.items_cursor.ItemsCursor(self, container_name, access_key, **kwargs)

    def new_session(self, access_key=None):
        return v3io.dataplane.session.Session(self, access_key or os.environ['V3IO_ACCESS_KEY'])

    def get_containers(self, access_key):
        """
        :return: Response
        """
        request_input = v3io.dataplane.input.GetContainersInput()

        return self._encode_and_http_request(None,
                                             access_key,
                                             request_input,
                                             v3io.dataplane.output.GetContainersOutput)

    def get_container_contents(self, container_name, access_key, **kwargs):
        """
        :key path:
        :key get_all_attributes:
        :key directories_only:
        :key limit:
        :key marker:
        :return: Response
        """
        request_input = v3io.dataplane.input.GetContainerContentsInput(**kwargs)

        return self._encode_and_http_request(container_name,
                                             access_key,
                                             request_input,
                                             v3io.dataplane.output.GetContainerContentsOutput)

    def get_object(self, container_name, access_key, **kwargs):
        request_input = v3io.dataplane.input.GetObjectInput(**kwargs)

        return self._encode_and_http_request(container_name,
                                             access_key,
                                             request_input)

    def put_object(self, container_name, access_key, **kwargs):
        request_input = v3io.dataplane.input.PutObjectInput(**kwargs)

        return self._encode_and_http_request(container_name,
                                             access_key,
                                             request_input)

    def delete_object(self, container_name, access_key, **kwargs):
        request_input = v3io.dataplane.input.DeleteObjectInput(**kwargs)

        return self._encode_and_http_request(container_name,
                                             access_key,
                                             request_input)

    def put_item(self, container_name, access_key, **kwargs):
        request_input = v3io.dataplane.input.PutItemInput(**kwargs)

        return self._encode_and_http_request(container_name,
                                             access_key,
                                             request_input)

    def put_items(self, container_name, access_key, **kwargs):
        request_input = v3io.dataplane.input.PutItemsInput(**kwargs)

        responses = v3io.dataplane.response.Responses()

        for item_path, item_attributes in future.utils.viewitems(request_input.items):
            # create a put item input
            put_item_input = v3io.dataplane.input.PutItemInput(
                v3io.common.helpers.url_join(request_input.path, item_path),
                item_attributes,
                request_input.condition)

            # encode it
            method, encoded_path, headers, body = put_item_input.encode(container_name, access_key)

            # add the response
            responses.add_response(self._http_request(method, encoded_path, headers, body))

        return responses

    def update_item(self, container_name, access_key, **kwargs):
        request_input = v3io.dataplane.input.UpdateItemInput(**kwargs)

        return self._encode_and_http_request(container_name,
                                             access_key,
                                             request_input)

    def get_item(self, container_name, access_key, **kwargs):
        request_input = v3io.dataplane.input.GetItemInput(**kwargs)

        return self._encode_and_http_request(container_name,
                                             access_key,
                                             request_input,
                                             v3io.dataplane.output.GetItemOutput)

    def get_items(self, container_name, access_key, **kwargs):
        request_input = v3io.dataplane.input.GetItemsInput(**kwargs)

        return self._encode_and_http_request(container_name,
                                             access_key,
                                             request_input,
                                             v3io.dataplane.output.GetItemsOutput)

    def create_stream(self, container_name, access_key, **kwargs):
        """
        :key path:
        :key shard_count:
        :key retention_period_hours:
        :return: Response
        """
        request_input = v3io.dataplane.input.CreateStreamInput(**kwargs)

        return self._encode_and_http_request(container_name,
                                             access_key,
                                             request_input)

    def delete_stream(self, container_name, access_key, **kwargs):
        """
        :key path:
        :return: Response
        """

        # TODO: delete shards

        return self.delete_object(container_name, access_key, **kwargs)

    def describe_stream(self, container_name, access_key, **kwargs):
        """
        :key path:
        :return: Response
        """
        request_input = v3io.dataplane.input.DescribeStreamInput(**kwargs)

        return self._encode_and_http_request(container_name,
                                             access_key,
                                             request_input,
                                             v3io.dataplane.output.DescribeStreamOutput)

    def seek_shard(self, container_name, access_key, **kwargs):
        """
        :key path:
        :key seek_type:
        :key starting_sequence_number:
        :key timestamp:
        :return: Response
        """
        request_input = v3io.dataplane.input.SeekShardInput(**kwargs)

        return self._encode_and_http_request(container_name,
                                             access_key,
                                             request_input,
                                             v3io.dataplane.output.SeekShardOutput)

    def put_records(self, container_name, access_key, **kwargs):
        """
        :key path:
        :key records:
        :return: Response
        """
        request_input = v3io.dataplane.input.PutRecordsInput(**kwargs)

        return self._encode_and_http_request(container_name,
                                             access_key,
                                             request_input,
                                             v3io.dataplane.output.PutRecordsOutput)

    def get_records(self, container_name, access_key, **kwargs):
        """
        :key path:
        :key location:
        :key limit:
        :return: Response
        """
        request_input = v3io.dataplane.input.GetRecordsInput(**kwargs)

        return self._encode_and_http_request(container_name,
                                             access_key,
                                             request_input,
                                             v3io.dataplane.output.GetRecordsOutput)

    def _http_request(self, method, path, headers=None, body=None):
        endpoint, connection_pool = self._get_next_connection_pool()

        self._logger.debug_with('Tx', method=method, path=path, headers=headers, body=body)

        response = connection_pool.request(method,
                                           endpoint + path,
                                           headers=headers,
                                           data=body,
                                           timeout=self._timeout,
                                           verify=False)

        self._logger.debug_with('Rx', status_code=response.status_code, headers=response.headers, body=response.text)

        return response

    def _get_endpoints(self, endpoints):
        if endpoints is None:
            env_endpoints = os.environ.get('V3IO_API')

            if env_endpoints is not None:
                endpoints = env_endpoints.split(',')
            else:
                raise RuntimeError('Endpoints must be passed to context or specified in V3IO_API')

        endpoints_with_scheme = []

        for endpoint in endpoints:
            if not endpoint.startswith('http://') and not endpoint.startswith('https://'):
                endpoints_with_scheme.append('http://' + endpoint)
            else:
                endpoints_with_scheme.append(endpoint)

        return endpoints_with_scheme

    def _create_connection_pools(self, endpoints, max_connections):
        connection_pools = []

        for endpoint in endpoints:
            connection_pools.append((endpoint, requests.Session()))

        return tuple(connection_pools)

    def _get_next_connection_pool(self):

        # TODO: multithreading safe
        endpoint, connection_pool = self._connection_pools[self._next_connection_pool]

        self._next_connection_pool += 1
        if self._next_connection_pool >= len(self._connection_pools):
            self._next_connection_pool = 0

        return endpoint, connection_pool

    def _encode_and_http_request(self,
                                 container_name,
                                 access_key,
                                 request_input,
                                 output=None):

        # get request params with the encoder
        method, path, headers, body = request_input.encode(container_name, access_key)

        # call the encoder to get the response
        response = self._http_request(method, path, headers, body)

        # create a response
        return v3io.dataplane.response.Response(output,
                                                response.status_code,
                                                headers,
                                                response.text)
