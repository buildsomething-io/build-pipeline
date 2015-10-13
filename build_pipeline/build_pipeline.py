#!/usr/bin/env python
""" Orchestrate a build pipeline

Components include:
* GitHub deployment and deployment status events
* AWS SQS queues subscribed to SNS Topics
* Jenkins servers configured with the GitHub SQS Plugin
* Jenkins jobs configured to post to the GitHub deployment and deployment status APIs
"""
from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer
import json
import os

from .helpers import SnsError, parse_webhook_payload, is_valid_gh_event  # pylint: disable=relative-import

import logging
import sys
LOGGER = logging.getLogger(__name__)

# Send the output to stdout so it will get handled with the Heroku logging service
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

# TODO: this isn't suppressing the logging, not sure why
logging.getLogger('requests').setLevel(logging.ERROR)
logging.getLogger('boto').setLevel(logging.ERROR)


class PipelineHttpRequestHandler(BaseHTTPRequestHandler):
    """
    Handler for the HTTP service.
    """
    protocol = "HTTP/1.1"

    def do_POST(self):  # pylint: disable=invalid-name
        """
        Respond to the HTTP POST request sent by GitHub WebHooks
        """
        # Send a response back to the webhook
        LOGGER.debug("Sending a 200 HTTP response back to the webhook")
        self.send_response(200)
        self.end_headers()

        # Retrieve the request POST json from the client as a dictionary.
        # If no POST json can be interpreted, don't do anything.
        try:
            length = int(self.headers.getheader('content-length'))
            contents = self.rfile.read(length)
            data = json.loads(contents)
        except (TypeError, ValueError):
            LOGGER.error("Could not interpret the POST request.")
            return

        event = self.headers.get('X-GitHub-Event')
        signature = self.headers.get('X-Hub-Signature')

        if is_valid_gh_event(signature, event, contents, data):
            try:
                LOGGER.debug("Received GitHub event: {}".format(event))
                parse_webhook_payload(event, data)

            except SnsError, err:
                LOGGER.error(str(err))


def run(server_class=HTTPServer, handler_class=PipelineHttpRequestHandler):  # pragma: no cover
    """ Start up a single-threaded server to handle the requests """
    port = int(os.environ.get('PORT', '0'))
    server_address = ('', port)
    httpd = server_class(server_address, handler_class)

    LOGGER.debug('Starting service on port {0}'.format(httpd.server_port))
    httpd.serve_forever()


if __name__ == "__main__":  # pragma: no cover
    if __package__ is None:
        sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    run()
