# import pytest
# from kubernetes import client, config, utils


NAMESPACE = "random-user-a"


user_config = {
    "app_name": "calculator",
    "git_url": "https://github.com/mnh-14/calculator-tester.git",
    "git_branch": "main",
    "dockerfile_path": "Dockerfile",

    "container_port": 8080,
    "namespace": NAMESPACE,
    "replicas": 2,
    "grace_period_seconds": 30,

    "cpu_request": "100m",
    "cpu_limit": "500m",
    "memory_request": "256Mi",
    "memory_limit": "512Mi",
}

build_passed = None

def create_namespace():
    # This will create the namespace names NAMESPACE, if it does not exist, using the deploy-service api call, post to /api/namespace
    # If it does exist, it will delete that namespace, using python kubernetes client, and then create it again using the deploy-service api call, post to /api/namespace
    pass


def check_build_status():
    # This will check the build status of the application, using the deploy-service api call, post to /api/build/status
    # It will do pooling every 30 seconds, and will print the status. Only when failed/successfull/unknown, 
    # it will print and then return the status.
    # If it is still building, it will print the status and then wait for 30 seconds and then check again.
    pass


def check_deployment_status():
    # This will check the deployment status of the application, using the deploy-service api call, post to /api/deploy/status
    # It will do pooling every 30 seconds, and will print the status. Only when failed/unknown/running, 
    # it will print and then return the status.
    # If it is still deploying, it will print the status and then wait for 30 seconds and then check again.
    pass

@pytest.mark.run(order=1)
def test_build_pipeline():
    # first create namespace
    # Then call the build api, post to /api/build with the user_config as json body
    # Then call the check_build_status function to check the build status
    # Use kubernetes client to check and fetch every log+description+underlying-configs of the build pod, print if it failed/unkown
    # and save the logs to a file named build_logs-<TIMESTAMP>.txt inside log folder.
    # assert that the build status is success/failed/unknown. if failed/unknown, fail the test.
    pass

@pytest.mark.run(order=2)
def test_deploy_pipeline():
    # Check if build_passed, if it's none/true, continue, if false then skip the test
    # Then call the deploy api, post to /api/deploy with the user_config as json body
    # Then call the check_deployment_status function to check the deployment status
    # Use kubernetes client to check and fetch every log+description+underlying-configs of the deployment pod, print if it failed/unkown
    # and save the logs to a file named deploy_logs-<TIMESTAMP>.txt inside log folder.
    # assert that the deployment status is running/failed/pending. if failed/unknown, fail the test.
    pass