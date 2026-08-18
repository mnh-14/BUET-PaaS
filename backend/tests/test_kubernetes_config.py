from deployment_config import RESOURCE_TIERS, build_deployer_config, kubernetes_name
from deployer.k3s_conf import JobPipelineBuilder


def test_kubernetes_name_is_dns_safe():
    assert kubernetes_name("My Cool_App") == "my-cool-app"
    assert kubernetes_name("2105001") == "2105001"


def test_small_medium_large_resolve_to_bounded_resources():
    for size, expected in RESOURCE_TIERS.items():
        project = {
            "project_id": "proj-1",
            "user_id": "2105001",
            "project_name": "My App",
            "repo_url": "https://github.com/student/app.git",
            "instance_size": size,
        }
        config = build_deployer_config(project, {"deployment_id": "dep-1"})
        for key, value in expected.items():
            assert config[key] == value
        assert config["namespace"] == "2105001"
        assert config["app_name"] == "my-app"


def test_private_clone_token_is_read_from_kubernetes_secret():
    builder = JobPipelineBuilder("app", namespace="2105001")
    builder.apply_git_cloner(
        "https://github.com/student/private.git",
        github_secret_name="github-clone-dep-1",
    )
    manifest = builder.build()
    environment = manifest["spec"]["template"]["spec"]["containers"][0]["env"]
    token = next(item for item in environment if item["name"] == "GITHUB_TOKEN")
    assert token["valueFrom"]["secretKeyRef"] == {
        "name": "github-clone-dep-1",
        "key": "token",
    }
    assert "value" not in token
