"""
Tests for the HTTP server
"""
from BaseHTTPServer import HTTPServer
from unittest import TestCase

import json
from mock import patch
from moto import mock_sns
import requests
import threading

from ..build_pipeline import PipelineHttpRequestHandler, parse_webhook_payload
from .utils import create_topic


class ThreadedHTTPServer(HTTPServer, object):
    """ HTTP server implementation for testing.

    Configure the server to listen on an arbitrary open port on localhost.
    Start it up in a separate thread so that it can be shutdown by another thread.
    """
    def __init__(self):
        """
        """
        address = ('0.0.0.0', 0)
        HTTPServer.__init__(self, address, PipelineHttpRequestHandler)

        server_thread = threading.Thread(target=self.serve_forever)
        server_thread.daemon = True
        server_thread.start()

    def shutdown(self):
        """
        Stop the server and free up the port
        """
        HTTPServer.shutdown(self)
        self.socket.close()

    @property
    def port(self):
        """
        Return the port that the service is listening on.
        """
        _, port = self.server_address
        return port


class PipelineServerTestCase(TestCase):
    """TestCase class for verifying the HTTP server that
    is servicing the webhooks from GitHub.
    """
    def setUp(self):
        """These tests start the server to test it. """
        super(PipelineServerTestCase, self).setUp()
        self.server = ThreadedHTTPServer()
        self.addCleanup(self.server.shutdown)
        self.url = "http://127.0.0.1:{port}".format(port=self.server.port)

    @patch("build_pipeline.build_pipeline.parse_webhook_payload")
    def test_github_event(self, mock_downstream):
        mock_downstream.return_value = 'foo'
        headers = {'X-GitHub-Event': 'foo', 'content-type': 'application/json'}
        payload = {'repository': 'bar'}
        response = requests.post(self.url, headers=headers, data=json.dumps(payload))
        self.assertEqual(response.status_code, 200)

    def test_get_request(self):
        """ Test that GET requests are not implemented, only POSTs are. """
        response = requests.get(self.url, data={})
        self.assertEqual(response.status_code, 501)


@patch('build_pipeline.helpers.HANDLED_REPO', 'foo/bar')
class PipelineHandlerTestCase(TestCase):
    """TestCase class for verifying the trigger handling. """

    def setUp(self):
        super(PipelineHandlerTestCase, self).setUp()
        self.handler = PipelineHttpRequestHandler

    def test_untriggered_repo(self):
        result = parse_webhook_payload('foo', {'repository': {'full_name': 'foo/untriggered'}})
        self.assertEqual(result, None)

    def test_untriggered_event(self):
        result = parse_webhook_payload('foo', {'repository': {'full_name': 'foo/bar'}})
        self.assertEqual(result, None)

    @mock_sns
    def test_deployment_event(self):
        with patch('build_pipeline.helpers.PROVISIONING_TOPIC', create_topic()):
            result = parse_webhook_payload(
                'deployment',
                {'repository': {'full_name': 'foo/bar'}, 'deployment': {}}
            )
            msg = 'Expected MessageID {} to be a 36 digit string'.format(result)
            self.assertEqual(len(result), 36, msg)

    def test_ignored_deployment_status_event(self):
        result = parse_webhook_payload(
            'deployment_status',
            {'repository': {'full_name': 'foo/bar'}, 'deployment': {}, 'deployment_status': {}}
        )
        self.assertEqual(result, None)

    @mock_sns
    def test_deployment_status_success_event(self):
        with patch('build_pipeline.helpers.SITESPEED_TOPIC', create_topic()):
            result = parse_webhook_payload(
                'deployment_status',
                {'repository': {'full_name': 'foo/bar'}, 'deployment': {}, 'deployment_status': {'state': 'success'}}
            )
            msg = 'Expected MessageID {} to be a 36 digit string'.format(result)
            self.assertEqual(len(result), 36, msg)
