"""Verify a disposable, revision-pinned Compose target before browser write tests."""
import argparse
import json
import re
import socket
import subprocess
from pathlib import Path
from urllib.request import urlopen

REVISION = re.compile(r"[0-9a-f]{40}")
PROJECT = re.compile(r"(?:weather-course-qa|c3-final)-[a-z0-9][a-z0-9-]{2,40}")
LOOPBACK = re.compile(r"http://127\.0\.0\.1:[1-9][0-9]{0,4}")
IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}")
IMAGE_ROLES = ("api", "frontend")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validated_revision(revision):
    return isinstance(revision, str) and REVISION.fullmatch(revision)


def valid_loopback(url):
    return isinstance(url, str) and LOOPBACK.fullmatch(url) and int(url.rsplit(":", 1)[-1]) <= 65535


def validate_browser_proof(proof, url, revision):
    """A fresh-target proof is not a signature; it is a safety check against mix-ups."""
    require(isinstance(proof, dict), "Expected a QA target object")
    project = proof.get("project")
    require(isinstance(project, str) and PROJECT.fullmatch(project), "Not a disposable QA project")
    require(validated_revision(revision) and proof.get("revision") == revision, "QA revision mismatch")
    require(proof.get("mysql_volume") == project + "_mysql_data", "Wrong QA MySQL volume")
    require(valid_loopback(proof.get("qa_url")) and valid_loopback(url), "QA URL must be a loopback port")
    require(proof.get("test_url", proof["qa_url"]) == url, "Wrong browser URL for verified QA target")
    for role in IMAGE_ROLES:
        digest = proof.get(f"{role}_image_id")
        require(isinstance(digest, str) and IMAGE_ID.fullmatch(digest), f"Missing verified {role} image ID")


def docker(*args):
    return subprocess.check_output(["docker", *args], encoding="utf-8").strip()


def image_manifest(revision):
    return {"revision": revision, **{
        f"{role}_image_id": json.loads(docker("image", "inspect", f"weather-course-{role}:{revision}"))[0]["Id"]
        for role in IMAGE_ROLES
    }}


def service(project, name):
    ids = docker("ps", "-q", "--filter", f"label=com.docker.compose.project={project}",
                 "--filter", f"label=com.docker.compose.service={name}").splitlines()
    require(len(ids) == 1, f"Expected one running {name} container in {project}")
    return json.loads(docker("inspect", ids[0]))[0]


def verify_target(fresh, manifest):
    project, port, revision = fresh["project"], fresh["port"], fresh["revision"]
    api, frontend, mysql = (service(project, name) for name in ("api", "frontend", "mysql"))
    require(manifest == image_manifest(revision), "Loaded API/frontend do not match the delivery image manifest")
    require(api["Image"] == manifest["api_image_id"] and frontend["Image"] == manifest["frontend_image_id"],
            "Running API/frontend do not match the delivery image manifest")
    require(frontend["NetworkSettings"]["Ports"].get("80/tcp") == [{"HostIp": "127.0.0.1", "HostPort": str(port)}],
            "The verified frontend does not own exactly the requested loopback binding")
    mount = [item for item in mysql["Mounts"] if item["Destination"] == "/var/lib/mysql"]
    volume = project + "_mysql_data"
    require(len(mount) == 1 and mount[0]["Type"] == "volume" and mount[0]["Name"] == volume, "QA MySQL volume mismatch")
    labels = json.loads(docker("volume", "inspect", volume))[0]["Labels"] or {}
    require(labels.get("com.docker.compose.project") == project and labels.get("com.docker.compose.volume") == "mysql_data",
            "QA volume not owned by this Compose project")
    url = f"http://127.0.0.1:{port}"
    with urlopen(url + "/build-revision.txt", timeout=5) as response:
        require(response.status == 200 and response.read(128).decode().strip() == revision, "Frontend revision mismatch")
    proof = {**manifest, "project": project, "qa_url": url, "mysql_volume": volume}
    validate_browser_proof(proof, url, revision)
    return proof


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("manifest", "preflight", "verify"))
    parser.add_argument("--revision", required=True)
    parser.add_argument("--project")
    parser.add_argument("--port", type=int)
    parser.add_argument("--fresh-proof", type=Path)
    parser.add_argument("--image-manifest", type=Path)
    a = parser.parse_args()
    try:
        require(validated_revision(a.revision), "Require the full candidate SHA")
        if a.action == "manifest":
            result = image_manifest(a.revision)
        else:
            require(a.project and PROJECT.fullmatch(a.project), "Require a new weather-course-qa-* project name")
            require(a.port and valid_loopback(f"http://127.0.0.1:{a.port}"), "Require a valid loopback port")
            fresh = {"project": a.project, "port": a.port, "revision": a.revision}
            if a.action == "preflight":
                label = f"label=com.docker.compose.project={a.project}"
                require(not docker("ps", "-aq", "--filter", label), "QA project already has containers")
                require(not docker("volume", "ls", "-q", "--filter", label), "QA project already has a volume")
                with socket.socket() as probe:
                    probe.bind(("127.0.0.1", a.port))
                result = fresh
            else:
                require(a.fresh_proof and a.image_manifest, "Both preflight and image proofs are required")
                require(json.loads(a.fresh_proof.read_text(encoding="utf-8-sig")) == fresh, "Fresh-project preflight mismatch")
                result = verify_target(fresh, json.loads(a.image_manifest.read_text(encoding="utf-8-sig")))
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"Unsafe QA target: {exc}") from exc
    print(json.dumps(result))


if __name__ == "__main__":
    main()
