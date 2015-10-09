"""
Tests for the helper methods
"""
from unittest import TestCase

from mock import patch
from moto import mock_sns

from .utils import create_topic
from ..helpers import publish_sns_messsage, SnsError, _compose_sns_message, parse_webhook_payload


@mock_sns
class SNSTestCase(TestCase):
    """TestCase class for verifying the helper methods. """

    def test_nonexistent_sns_topic_arn(self):
        # There are no topics yet in the mocked SNS, so using
        # any arn will raise an error
        self.assertRaisesRegexp(SnsError, 'BotoServerError: 404 Not Found.*', publish_sns_messsage, 'arn', 'msg')

    def test_publish_to_topic(self):
        # Create a mocked connection and create the topic then
        # publish a message to that topic
        topic_arn = create_topic()
        msg_id = publish_sns_messsage(topic_arn=topic_arn, message='foo')
        self.assertIsNotNone(msg_id)


class HelperTestCase(TestCase):
    """TestCase class for verifying the helper methods. """
    def test_compose_message(self):
        msg = _compose_sns_message('org', 'repo')
        self.assertEqual(
            msg,
            {'default': '{"owner": {"name": "org"}, "url": "https://github.com/org/repo", "name": "repo"}'}
        )

    @patch('build_pipeline.helpers.HANDLED_REPO', 'org/repo')
    @patch('build_pipeline.helpers.publish_sns_messsage')
    def test_webhook_payload_handled(self, mock_publish):
        mock_publish.return_value = 'foo'
        payload = {'repository': {'full_name': 'org/repo'}}

        result = parse_webhook_payload('deployment', payload)
        self.assertEqual(result, 'foo')

    @patch('build_pipeline.helpers.HANDLED_REPO', 'org/repo')
    def test_webhook_payload_unhandled_event(self):
        payload = {'repository': {'full_name': 'org/repo'}}

        result = parse_webhook_payload('foo', payload)
        self.assertEqual(result, None)

    def test_webhook_payload_unhandled_repo(self):
        payload = {'repository': {'full_name': 'org/repo'}}

        result = parse_webhook_payload('deployment', payload)
        self.assertEqual(result, None)

    def test_webhook_payload_bad_payload(self):
        payload = "string"

        result = parse_webhook_payload('deployment', payload)
        self.assertEqual(result, None)
