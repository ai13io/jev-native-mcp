# Contributing

Contributions are welcome when they keep the project small, typed, portable,
and explicit about hosted data flow.

## Before opening a change

- Use an issue for substantial changes to tool schemas, security boundaries,
  storage, deployment, or provider behavior.
- Use [SECURITY.md](SECURITY.md) for vulnerabilities; do not publish exploit
  details in an issue or pull request.
- Keep unrelated changes in separate pull requests.

## Development setup

Jev Native MCP requires Python 3.10 or newer.

```bash
python -m venv server/.venv
```

Activate the environment using the command for your platform, then install the
development dependencies:

```bash
server/.venv/bin/python -m pip install -e "./server[dev]"
```

On Windows, replace `server/.venv/bin/python` with
`& ".\server\.venv\Scripts\python.exe"`.

The unit suite mocks provider behavior and must not require a TypeSafe key or
network access. Run the repository checks from the project root:

```bash
server/.venv/bin/python -m pytest server/tests
server/.venv/bin/python -m pytest tools/test_configure_profile.py
server/.venv/bin/python -m pytest scripts/test_package_portable.py
server/.venv/bin/python -m pytest skills/jev-pentest/scripts/test_public_source_audit.py
server/.venv/bin/python -m pytest skills/jev-pentest/scripts/test_evaluate_source_audit.py
server/.venv/bin/python scripts/verify_release.py
```

This is the canonical local test route and matches the suites listed in the
README and CI workflow.

Build a release candidate outside the source root:

```bash
server/.venv/bin/python scripts/package_portable.py \
  --output ../dist/jev-native-0.4.0.zip
```

Review `release-files.txt`, `PACKAGE-MANIFEST.json`, the resulting SHA-256, and
the extracted archive before distribution. Selected credential-pattern checks
are a tripwire, not a complete secret or confidentiality classifier.

Live fixtures under `server/evals/fixtures/` are separate. They require a
running server, consume provider quota, and must use only reviewed public or
synthetic content.

## Design rules

Changes must preserve these boundaries:

1. Hosted inputs are limited to `public` and `synthetic` data.
2. A loopback or private-network MCP route still forwards accepted decision
   payloads to the hosted provider.
3. Tools that send supplied content to TypeSafe are not annotated read-only.
4. Jev results are advisory and cannot authorize, execute, delete, submit, or
   make a final security decision.
5. Batched tools preserve every stable input ID and reject incomplete output.
6. Malformed, missing, or unexpected provider fields fail loudly.
7. Receipt files contain operational metadata and keyed request digests, never
   request payloads, prompts, source text, paths, identifier lists, or free-form
   notes.
8. Credentials and runtime state never enter source control or release bundles.
9. The server remains bound to loopback or an explicit private IP unless a
   separately reviewed authenticated HTTPS boundary is implemented.

Use deterministic code for parsing, hashes, dates, counts, arithmetic,
allowlists, and hard policy. Do not add model calls where a reliable
deterministic rule already exists.

## Tests

Add or update tests for every behavior change. Depending on the change, cover:

- request bounds and type validation;
- sensitive-content rejection before provider calls;
- strict upstream response validation;
- stable-ID and complete-set preservation;
- ties at ranking cutoffs;
- budget preflight and provider failures;
- receipt schemas, permissions, payload absence, internal row-chain validation,
  and the documented inability to detect valid-tail truncation without an
  external authenticated head;
- private bind enforcement and client-visible annotations;
- deterministic, inventory-bounded release packaging with selected credential
  checks; and
- cross-platform path behavior; service behavior must be labeled unverified
  until exercised on that platform.

Do not weaken a test to accommodate ambiguous output. Fix the contract or make
the failure explicit.

## Documentation

Documentation should be concise, verifiable from the repository, and clear
about egress and limitations. Avoid unmeasured performance claims, guarantees
about semantic correctness, or examples containing real credentials, private
data, active targets, or internal paths.

Update `CHANGELOG.md` for user-visible changes. Update every affected deployment
guide when configuration or service behavior changes.

## Pull request checklist

- [ ] The change is focused and has an explanatory commit message.
- [ ] Unit and release checks pass.
- [ ] No secret, private fixture, runtime ledger, result archive, or environment
      directory is included.
- [ ] New hosted egress is disclosed in tool annotations and documentation.
- [ ] Input and output schemas remain bounded and fail closed.
- [ ] Documentation and changelog entries match the implemented behavior.
- [ ] Platform-specific effects are tested or explicitly documented.

By contributing, you agree that your contribution is licensed under the
Apache License 2.0 used by this repository.
