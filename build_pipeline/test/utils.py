""" Utility methods for tests. """
from boto import connect_sns


def create_topic():
    """ Create a topic so that we can publish to it. """
    conn = connect_sns()
    conn.create_topic("some-topic")
    topics_json = conn.get_all_topics()
    topic_arn = topics_json["ListTopicsResponse"]["ListTopicsResult"]["Topics"][0]['TopicArn']
    return topic_arn
