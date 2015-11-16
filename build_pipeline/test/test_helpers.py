"""
Tests for the helper methods
"""
import hashlib
import hmac
import json
from unittest import TestCase

from mock import patch
from moto import mock_sns

from .utils import create_topic
from ..helpers import publish_sns_messsage, SnsError, parse_webhook_payload, is_valid_gh_event
from ..helpers import _compose_sns_message


@mock_sns
class SNSTestCase(TestCase):
    """TestCase class for verifying helper methods that use SNS."""

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


class ComposeTestCase(TestCase):
    """TestCase class for verifying the method that composes the message."""
    def test_compose_message_default_ci_data(self):
        msg = _compose_sns_message('org', 'repo')
        self.assertEqual(
            msg,
            {"repository": {"owner": {"name": "org"}, "url": "https://github.com/org/repo", "name": "repo"},
             "ci_data": {}}
        )

    def test_compose_message_with_ci_data(self):
        ci_data = {'sha_to_build': '123456789'}
        msg = _compose_sns_message('org', 'repo', ci_data=ci_data)
        self.assertEqual(msg, {
            "repository": {"owner": {"name": "org"}, "url": "https://github.com/org/repo", "name": "repo"},
            "ci_data": ci_data
        })


class ParsePayloadTestCase(TestCase):
    """TestCase class for verifying the helper method for parsing the payload."""
    def setUp(self):
        super(ParsePayloadTestCase, self).setUp()
        self.payload = {
            'repository': {'full_name': 'org/repo'},
            'deployment': {'id': '1234'}
        }

    @patch('build_pipeline.helpers.HANDLED_REPO', 'org/repo')
    @patch('build_pipeline.helpers.publish_sns_messsage')
    def test_webhook_payload_handled(self, mock_publish):
        mock_publish.return_value = 'foo'
        result = parse_webhook_payload('deployment', self.payload)
        self.assertEqual(result, 'foo')

    @patch('build_pipeline.helpers.HANDLED_REPO', 'org/repo')
    def test_webhook_payload_unhandled_event(self):
        result = parse_webhook_payload('foo', self.payload)
        self.assertEqual(result, None)

    def test_webhook_payload_unhandled_repo(self):
        result = parse_webhook_payload('deployment', self.payload)
        self.assertEqual(result, None)

    def test_webhook_payload_bad_payload(self):
        string_payload = "string"
        result = parse_webhook_payload('deployment', string_payload)
        self.assertEqual(result, None)


class GitHubEventTestCase(TestCase):
    """TestCase class for verifying GitHub events."""
    def test_no_signature(self):
        result = is_valid_gh_event(None, 'my_event', 'abc', {'repository': {'full_name': 'hello'}})
        self.assertFalse(result)

    def test_no_event(self):
        result = is_valid_gh_event('sha1=foo', None, 'abc', {'repository': {'full_name': 'hello'}})
        self.assertFalse(result)

    def test_no_repo(self):
        result = is_valid_gh_event('sha1=foo', 'my_event', 'abc', {'repository': {}})
        self.assertFalse(result)

    def test_wrong_sig_string(self):
        result = is_valid_gh_event('xyz=foo', 'my_event', 'abc', {'repository': {'full_name': 'hello'}})
        self.assertFalse(result)

    @patch('build_pipeline.helpers.WEBHOOK_SECRET_TOKEN', 'my_token')
    def test_incorrect_signature(self):
        data = {'repository': {'full_name': 'hello'}}
        contents = json.dumps(data)
        result = is_valid_gh_event('sha1=something_else', 'my_event', contents, data)
        self.assertFalse(result)

    @patch('build_pipeline.helpers.WEBHOOK_SECRET_TOKEN', 'my_token')
    def test_good_signature(self):
        data = {'repository': {'full_name': 'hello'}}
        contents = json.dumps(data)
        my_hash = hmac.new('my_token', msg=contents, digestmod=hashlib.sha1).hexdigest()
        result = is_valid_gh_event('sha1={}'.format(my_hash), 'my_event', contents, data)
        self.assertTrue(result)
