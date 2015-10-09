# build-pipeline
EdX Engineering Build Pipeline orchestration

Use GitHub webhook events to trigger CI/CD pipeline jobs by inspecting the payload
and posting to SNS to trigger various jenkins jobs.

To test out locally:

Set up a python virtualenv and pip install into it, or install the python requirements globally with:
```
sudo pip install -r requirements.txt
```
Start up the server, listening on a port specified by the value of a system environment variable named PORT:
```
PORT=8888 build_pipeline/build_pipeline.py
```
Manually make a request similar to one that would be sent via a WebHook. Substitue the payload below with an event that will trigger the logic that you had coded by modifying the redirect script:
```
curl -X PUT -d '{ "ref": "master", "payload": "{\"user\":\"atmos\",\"room_id\":123456}", "description": "foo" }' http://localhost:8888
```
To deploy on heroku:

* On heroku, follow the instructions for deploying a python app on the cedar stack (free).
* In the heroku app dashboard, under Settings, add Config var values for environment variables that the application needs. These can be found at the top of the build-pipeline/helpers.py file.
* You can now test out the web application with the above curl statement, using the URL of your heroku app instead
of localhost. Either http or https will work; heroku handles the routing for you.

Verifying the code:

First install the requirements:
```
pip install -r test-requirements.txt
```
To check for pep8 violations:
```
pep8 .
```
To run all tests:
```
nosetests
```
To run a single test, add the testspec to the nosetests command. Here are some examples:
```
nosetests build_pipeline/test/test_helpers.py
nosetests build_pipeline/test/test_helpers.py:HelperTestCase
nosetests build_pipeline/test/test_helpers.py:HelperTestCase.test_publish_to_topic
```
