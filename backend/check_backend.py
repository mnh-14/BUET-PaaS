#!/usr/bin/env python3
import argparse
import sys
import time

try:
    import requests
except Exception:
    requests = None
    import urllib.request
    import urllib.error
import json
import re


def http_get(url, timeout=5):
    if requests:
        r = requests.get(url, timeout=timeout)
        return r.status_code, r.text
    else:
        try:
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                return resp.getcode(), resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8") if getattr(e, 'fp', None) else ""
            return e.code, body
        except Exception:
            raise


def http_request(url, method='GET', timeout=5, json_body=None, headers=None):
    headers = headers or {}
    if requests:
        try:
            if method.upper() == 'GET':
                r = requests.get(url, timeout=timeout, headers=headers)
            elif method.upper() == 'POST':
                r = requests.post(url, json=json_body, timeout=timeout, headers=headers)
            else:
                r = requests.request(method, url, json=json_body, timeout=timeout, headers=headers)
            return r.status_code, r.text
        except requests.RequestException as e:
            # requests may embed response info
            if getattr(e, 'response', None) is not None:
                return e.response.status_code, e.response.text
            raise
    else:
        data = None
        if json_body is not None:
            data = json.dumps(json_body).encode('utf-8')
            headers = dict(headers)
            headers['Content-Type'] = headers.get('Content-Type', 'application/json')
        req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.getcode(), resp.read().decode('utf-8')
        except urllib.error.HTTPError as e:
            body = e.read().decode('utf-8') if getattr(e, 'fp', None) else ""
            return e.code, body
        except Exception:
            raise


def check_endpoint(base, path, timeout):
    url = base.rstrip("/") + path
    try:
        code, body = http_get(url, timeout=timeout)
        ok = (200 <= code < 400)
        return ok, code, url
    except Exception:
        return False, None, url


def fetch_openapi_operations(base, openapi_path='/openapi.json', timeout=5):
    """Fetch OpenAPI JSON and return list of operations: dicts with keys
    'path', 'method', and optional 'example' (for POST bodies).
    """
    url = base.rstrip('/') + openapi_path
    try:
        code, body = http_get(url, timeout=timeout)
    except Exception:
        return []
    if not (200 <= code < 400):
        return []
    try:
        spec = json.loads(body)
    except Exception:
        return []

    ops = []
    for raw_path, methods in spec.get('paths', {}).items():
        for m, info in methods.items():
            method = m.upper()
            if method not in ('GET', 'POST'):
                continue

            # build example JSON for POST when possible
            example = None
            if method == 'POST' and info is not None:
                rb = info.get('requestBody') or {}
                content = rb.get('content', {})
                appjson = content.get('application/json') or {}
                # direct example
                if 'example' in appjson:
                    example = appjson['example']
                elif 'examples' in appjson and isinstance(appjson['examples'], dict):
                    # take first example value
                    ex = next(iter(appjson['examples'].values()))
                    example = ex.get('value') if isinstance(ex, dict) else None
                else:
                        schema = appjson.get('schema') or {}
                        props = schema.get('properties') or {}
                        if props:
                            body = {}
                            for name, meta in props.items():
                                lname = name.lower()
                                if 'id' in lname or 'port' in lname:
                                    body[name] = 1
                                elif 'email' in lname:
                                    body[name] = '2105085@cse.buet.ac.bd'
                                elif 'password' in lname:
                                    body[name] = 'secret'
                                elif 'name' in lname:
                                    body[name] = 'Test User'
                                elif 'repo' in lname or 'url' in lname:
                                    body[name] = 'https://github.com/Suprio85/Devops'
                                else:
                                    body[name] = 'test'
                            example = body

                # if we still don't have an example, provide sensible defaults for known endpoints
                if example is None:
                    if '/api/v1/users/login' in raw_path:
                        example = {'user_id': '2105085', 'password': 'secret'}
                    elif raw_path.rstrip('/') == '/api/v1/users':
                        example = {
                            'user_id': '2105085',
                            'name': 'Test User',
                            'email': '2105085@cse.buet.ac.bd',
                            'password': 'secret'
                        }
                    elif raw_path.rstrip('/') == '/api/v1/projects':
                        example = {
                            'repo_url': 'https://github.com/Suprio85/Devops',
                            'user_id': '2105085',
                            'project_name': 'my-project'
                        }

            # replace path params
            def replace_param(m):
                    name = m.group(1)
                    n = name.lower()
                    if 'user' in n:
                        return '2105085'
                    if 'project' in n:
                        return 'proj-test1234'
                    if 'deployment' in n:
                        return 'dep-test1234'
                    if 'id' in n or 'port' in n:
                        return '1'
                    return 'test'

            p = raw_path
            if not p.startswith('/'):
                p = '/' + p
            p = re.sub(r'{([^/}]+)}', lambda m: replace_param(m), p)
            p = re.sub(r'//+', '/', p)

            ops.append({'path': p, 'method': method, 'example': example})

    # dedupe by (path,method)
    seen = set()
    out = []
    for o in ops:
        key = (o['path'], o['method'])
        if key not in seen:
            seen.add(key)
            out.append(o)
    return out


def seed_test_data(base, timeout=5):
    """Create a test user and project. Returns dict with user_id, project_id, deployment_id when available."""
    results = {}
    # create user
    user_payload = {
        'user_id': '2105085',
        'name': 'Test User',
        'email': '2105085@cse.buet.ac.bd',
        'password': 'secret'
    }
    url_user = base.rstrip('/') + '/api/v1/users'
    code, body = http_request(url_user, method='POST', timeout=timeout, json_body=user_payload)
    if code in (200, 201):
        try:
            j = json.loads(body)
            results['user_id'] = j.get('user_id', user_payload['user_id'])
        except Exception:
            results['user_id'] = user_payload['user_id']
    elif code == 409:
        results['user_id'] = user_payload['user_id']
    else:
        # continue anyway; caller can inspect
        results['user_id'] = user_payload['user_id']

    # create project
    proj_payload = {
        'repo_url': 'https://github.com/Suprio85/Devops',
        'user_id': results['user_id'],
        'project_name': 'my-project'
    }
    url_proj = base.rstrip('/') + '/api/v1/projects'
    code, body = http_request(url_proj, method='POST', timeout=timeout, json_body=proj_payload)
    if code in (200, 201, 202):
        try:
            j = json.loads(body)
            results['project_id'] = j.get('project_id') or proj_payload.get('project_id')
            results['deployment_id'] = j.get('deployment_id')
        except Exception:
            # if body isn't JSON (202 may return plain text), leave placeholders
            results.setdefault('project_id', 'proj-test1234')
            results.setdefault('deployment_id', 'dep-test1234')
    else:
        # fallback placeholders
        results.setdefault('project_id', 'proj-test1234')
        results.setdefault('deployment_id', 'dep-test1234')

    return results


def main():
    p = argparse.ArgumentParser(description="Check backend health endpoints")
    p.add_argument("--host", default="127.0.0.1", help="Backend host (default: 127.0.0.1)")
    p.add_argument("--port", default=8000, type=int, help="Backend port (default: 8000)")
    p.add_argument("--all", action="store_true", help="Check all routes listed in OpenAPI /openapi.json")
    p.add_argument("--openapi-path", default='/openapi.json', help="OpenAPI JSON path (default: /openapi.json)")
    p.add_argument("--seed", action="store_true", help="Create a test user and project before running checks")
    p.add_argument("--retries", default=3, type=int, help="Number of retries (default: 3)")
    p.add_argument("--delay", default=2.0, type=float, help="Delay between retries seconds (default: 2)")
    p.add_argument("--timeout", default=5.0, type=float, help="HTTP timeout seconds (default: 5)")
    args = p.parse_args()

    base = f"http://{args.host}:{args.port}"
    endpoints = ["/", "/health"]

    if args.all:
        print(f"Fetching OpenAPI operations from {base}{args.openapi_path} ...")
        ops = fetch_openapi_operations(base, openapi_path=args.openapi_path, timeout=args.timeout)
        if not ops:
            print("Could not fetch OpenAPI operations — falling back to default endpoints")
        else:
            # build endpoints list of tuples (path, method, example)
            endpoints = ops

    # Optionally seed a test user/project so GETs don't 404 and POSTs validate
    created_ids = {}
    if args.seed:
        print("Seeding test user and project...")
        try:
            created_ids = seed_test_data(base, timeout=args.timeout)
            print(f"Seeded: {created_ids}")
        except Exception as e:
            print(f"Seeding failed: {e}")

    all_ok = True
    # If we seeded, substitute placeholder ids in ops and examples
    if isinstance(endpoints, list) and endpoints and isinstance(endpoints[0], dict) and created_ids:
        for op in endpoints:
            if 'path' in op:
                op['path'] = op['path'].replace('proj-test1234', created_ids.get('project_id', 'proj-test1234'))
                op['path'] = op['path'].replace('dep-test1234', created_ids.get('deployment_id', 'dep-test1234'))
                op['path'] = op['path'].replace('2105085', created_ids.get('user_id', '2105085'))
            if op.get('example') and isinstance(op['example'], dict):
                def deep_replace(obj):
                    if isinstance(obj, dict):
                        return {k: deep_replace(v) for k, v in obj.items()}
                    if isinstance(obj, list):
                        return [deep_replace(v) for v in obj]
                    if isinstance(obj, str):
                        return obj.replace('proj-test1234', created_ids.get('project_id', 'proj-test1234')).replace('dep-test1234', created_ids.get('deployment_id', 'dep-test1234')).replace('2105085', created_ids.get('user_id', '2105085'))
                    return obj
                op['example'] = deep_replace(op['example'])

    for entry in endpoints:
        # entry may be a simple path string (default) or an op dict when --all
        if isinstance(entry, dict):
            path = entry['path']
            method = entry.get('method', 'GET')
            example = entry.get('example')
        else:
            path = entry
            method = 'GET'
            example = None

        ok = False
        for attempt in range(1, args.retries + 1):
            try:
                url = base.rstrip('/') + path
                code, body = http_request(url, method=method, timeout=args.timeout, json_body=example)
                passed = (200 <= code < 400)
            except Exception:
                passed = False
                code = None
                url = base.rstrip('/') + path

            # Treat 409 Conflict for create endpoints as acceptable (resource already exists)
            if not passed and method == 'POST' and code == 409:
                # consider POST to /api/v1/users and /api/v1/projects as OK when 409
                if url.rstrip('/').endswith('/api/v1/users') or url.rstrip('/').endswith('/api/v1/projects'):
                    print(f" {method} {url} -> {code} (already exists)")
                    ok = True
                    break

            if passed:
                print(f" {method} {url} -> {code}")
                ok = True
                break
            else:
                print(f"✗ {method} {url} (attempt {attempt}/{args.retries}) -> {code}")
                if attempt < args.retries:
                    time.sleep(args.delay)

        if not ok:
            all_ok = False

    if all_ok:
        print("All checks passed")
        sys.exit(0)
    else:
        print("One or more checks failed")
        sys.exit(2)


if __name__ == "__main__":
    main()
