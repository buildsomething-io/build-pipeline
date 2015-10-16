# build-pipeline
EdX Engineering Build Pipeline orchestration

Use GitHub webhook events to trigger CI/CD pipeline jobs by inspecting the payload
and posting to SNS to trigger various jenkins jobs.

To deploy on heroku:

* On heroku, follow the instructions for deploying a python app on the cedar stack (free).
* In the heroku app dashboard, under Settings, add Config var values for environment variables that the application needs. These can be found at the top of the build-pipeline/helpers.py file.

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
