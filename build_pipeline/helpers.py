"""
Helper methods for triggering the next step in the deployment pipeline
"""
import hashlib
import hmac
import json
import os

from boto import connect_sns
from boto.exception import BotoServerError

import logging
LOGGER = logging.getLogger(__name__)

PIPELINE_REPO_ORG = os.environ.get('PIPELINE_REPO_ORG', 'foo')
PIPELINE_REPO_NAME = os.environ.get('PIPELINE_REPO_NAME', 'bar')
HANDLED_REPO = '{org}/{name}'.format(org=PIPELINE_REPO_ORG, name=PIPELINE_REPO_NAME)

# The unique ARNs (Amazon Resource Name) for the SNS topics
PROVISIONING_TOPIC = os.environ.get('PROVISIONING_TOPIC', 'insert_sns_arn_here')
SITESPEED_TOPIC = os.environ.get('SITESPEED_TOPIC', 'insert_sns_arn_here')

# The Jenkins jobs for triggering the builds
PROVISIONING_JOB = os.environ.get('PROVISIONING_JOB', 'prov_job')
SITESPEED_JOB = os.environ.get('SITESPEED_JOB', 'sitespeed_job')

# The string you want to use as the secret key for the webhook. This same string
# must be entered as the Secret in the GitHub repo webhook settings.
WEBHOOK_SECRET_TOKEN = os.environ.get('WEBHOOK_SECRET_TOKEN', 'insert_webhook_secret_here').encode('utf-8')


class SnsError(Exception):
    """ Error in the communication with SNS. """
    pass


def parse_webhook_payload(event, data):
    """Parse the WebHook payload and trigger downstream jobs.

    Args:
        event (string): GitHub event
        data (dict): payload from the webhook

    Returns:
        None if no downstream action is required
        string: MessageId of the published SNS message if a followon action should be taken
    """
    try:
        repo = data.get('repository')
        repo_name = repo.get('full_name')
    except (AttributeError, KeyError) as _err:
        LOGGER.error('Invalid webhook payload: {}'.format(data))
        return None

    if repo_name != HANDLED_REPO:
        # We only want to take action on a specific repo, so
        # even if another repo gets configured to send webhooks
        # to this app send back a 200 to GitHub
        LOGGER.debug('Unhandled repo: {}'.format(repo_name))
        return None

    msg_id = None

    # Handle deployment events
    if event == 'deployment':
        LOGGER.debug('Deployment event passed to the handler.')
        msg_id = handle_deployment_event(
            PROVISIONING_TOPIC,
            PIPELINE_REPO_ORG,
            PIPELINE_REPO_NAME,
            data.get('deployment')
        )

    # Handle deployment status events
    elif event == 'deployment_status':
        LOGGER.debug('Deployment status event passed to the handler.')
        msg_id = handle_deployment_status_event(
            SITESPEED_TOPIC,
            PIPELINE_REPO_ORG,
            PIPELINE_REPO_NAME,
            data.get('deployment'),
            data.get('deployment_status')
        )

    else:
        LOGGER.debug('{} events do not need to be handled.'.format(event))

    return msg_id


def is_valid_gh_event(signature, event, contents, data):
    """ Verify that the webhook sent conforms to the GitHub API v3.
    Args:
        signature (string): GitHub signature, from the request header
        event (string): GitHub event, from the request header
        contents (string): contents of the request
        data (dict): payload from the webhook

    Returns:
        True for valid GitHub events
        False otherwise
    """
    secret = WEBHOOK_SECRET_TOKEN
    if not signature:
        # This is not a valid webhook from GitHub because
        # those all send an X-Hub-Signature header.
        LOGGER.error('The X-Hub-Signature header was not received in the request.')
        return False

    if not event:
        # This is not a valid webhook from GitHub because
        # those all send an X-GitHub-Event header.
        LOGGER.error('The X-GitHub-Event header was not received in the request.')
        return False

    repo = data.get('repository')
    if not repo:
        # This is not a valid webhook from GitHub because
        # those all return the repository info in the JSON payload
        LOGGER.error('Invalid webhook payload: {}'.format(data))
        return False

    sha_name, gh_hash = signature.split('=')
    if sha_name != 'sha1':
        # A GitHub hash signature starts with sha1=, using the key
        # of your secret token and your payload body.
        LOGGER.error('Invalid X-Hub-Signature header: {}'.format(signature))
        return False

    computed_hash = hmac.new(secret, msg=contents, digestmod=hashlib.sha1).hexdigest()
    # Note that compare_digest was backported to Python 2 in 2.7.7,
    # so that is the minimum version of Python required.
    if not hmac.compare_digest(gh_hash, computed_hash):
        msg = '{} {} {}'.format(
            'The received WebHook payload was not signed with the WEBHOOK_SECRET_TOKEN.',
            'Received hash: {}'.format(gh_hash),
            'Computed hash: {}'.format(computed_hash)
        )
        LOGGER.error(msg)
        return False

    return True


def publish_sns_messsage(topic_arn, message):
    """ Publish a message to SNS that will trigger jenkins jobs listening via SQS subscription.

    Args:
        topic_arn (string): The arn representing the topic
        message (string): The message to send
        ci_data (dict): Metadata to pass to the CI system

    Returns:
        string: The MessageId of the published message

    Raises:
        SnsError when publishing was unsuccessful
    """
    try:
        # Dump the json object into a string.
        # This will handle the parameter strings correctly rather than submitting them with a u' prefix.
        message = json.dumps(message)
        LOGGER.debug('Publishing to {}. Message is {}'.format(topic_arn, message))
        conn = connect_sns()
        response = conn.publish(topic=topic_arn, message=message)

    except BotoServerError as err:
        raise SnsError(err)

    # A successful response will be something like this:
    # {u'PublishResponse':
    #     {u'PublishResult':
    #         {u'MessageId': u'46c3689d-9ca0-425e-a9a7-1ec036eec857'},
    #          u'ResponseMetadata': {u'RequestId': u'384ac68d-3775-11df-8963-01868b7c937a'
    #         }
    #     }
    # }
    try:
        message_id = response.get('PublishResponse').get('PublishResult').get('MessageId')
    except (AttributeError, KeyError) as _err:
        message_id = None

    if not message_id:
        raise SnsError('Could not publish message. Response was: {}'.format(response))

    LOGGER.debug('Successfully published MessageId {}'.format(message_id))
    return message_id


def _compose_sns_message(repo_org, repo_name, custom_data=None):
    """ Compose the message to publish to the SNS topic.

    Note that an SQS queue must be subscribed to the SNS topic, the Jenkins main configuration
    must be set up to be listening to that queue.

    The Jenkins SQS plugin will then consume messages from the SQS Queue.
    Two message formats are available:
    * default message format: this will trigger any jobs that have a matching github repository configuration
    * custom message format: Signalled by a custom_format object of any value, this must also contain
        the name of the job to trigger, and can optionally contain parameters to pass to the job.

    """
    if not custom_data:
        repo = {}
        repo['name'] = repo_name
        repo['owner'] = {'name': '{org}'.format(org=repo_org)}
        repo['url'] = 'https://github.com/{org}/{name}'.format(org=repo_org, name=repo_name)
        return {'repository': repo}

    elif not isinstance(custom_data, dict):
        raise ValueError('Custom data must be passed as a dict')

    custom_data['custom_format'] = True
    return custom_data


def _compose_custom_data(deployment):
    """ Compose the metadata to pass to the CI system.

    Args:
        deployment (dict): deployment object from the webhook payload

    Returns:
        dict: data to include in the message to the CI system
    """
    return {
        'parameters': [
            {'name': 'deployment_id', 'type': 'string', 'value': deployment.get('id', '')},
            {'name': 'sha', 'type': 'string', 'value': deployment.get('sha', '')},
            {'name': 'task', 'type': 'string', 'value': deployment.get('task', '')},
            {'name': 'environment', 'type': 'string', 'value': deployment.get('environment', '')}
        ]
    }


def handle_deployment_event(topic, repo_org, repo_name, deployment):
    """Handle the deployment event webhook.

    Technical implementation notes:
        * A successful quality build of master sends a request to create a deployment
          with required contexts. After the required contexts all pass,
          GitHub will send the DeploymentEvent webhook.
        * The Jenkins SQS plugin will look to trigger a build for any job that is configured
          with a Git backed (either directly or through a multi-SCM choice) repo that
          matches the URL, name, and owner specified in the message.
        * It will then look for unbuilt changes in that repo, as Jenkins does for any triggered build

    Args:
        repo_org (string): Org of the repo to use in the message
        repo_name (string): Name of the repo to use in the message
        deployment (dict): deployment object from the webhook payload

    Returns:
        string: the message ID of the published message
    """
    # Start up the pipeline by publishing an SNS message that will trigger the provisioning job.
    # At the moment we don't need any conditional logic for this. That is, for any
    # deployment event that is created, trigger the provisioning job.
    #
    # The provisioning job will need to post a deployment status event with 'state' equal to
    # 'success' in order to trigger the next job in the pipeline.
    LOGGER.info('Received deployment event')
    LOGGER.debug(deployment)
    custom_data = _compose_custom_data(deployment)
    custom_data['job'] = PROVISIONING_JOB
    message = _compose_sns_message(repo_org, repo_name, custom_data)
    msg_id = publish_sns_messsage(topic_arn=topic, message=message)
    return msg_id


def handle_deployment_status_event(topic, repo_org, repo_name, deployment, deployment_status):
    """Handle the deployment status event.

    This webhook is triggered by jenkins creating a deployment status event
    after a successful build provisioning the target sandbox.

    Args:
        repo_org (string): Org of the repo to use in the message
        repos_name (string): Name of the repo to use in the message
        deployment (dict): deployment object from the webhook payload
        deployment_status (dict): deployment status object from the webhook payload

    Returns:
        None if no action was required or
        string: the message ID of the published message
    """
    LOGGER.info('Received deployment status event:')
    LOGGER.debug(deployment_status)
    LOGGER.debug('For the deployment:')
    LOGGER.debug(deployment)

    state = deployment_status.get('state')

    if state == 'success':
        custom_data = _compose_custom_data(deployment)
        custom_data['job'] = SITESPEED_JOB

        # Continue the next job in the pipeline by publishing an SNS message that will trigger
        # the sitespeed job.
        message = _compose_sns_message(repo_org, repo_name, custom_data)
        msg_id = publish_sns_messsage(topic_arn=topic, message=message)
        return msg_id

    return None
