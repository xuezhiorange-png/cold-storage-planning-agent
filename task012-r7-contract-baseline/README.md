# TASK-012 R7 contract baseline transport

This artifact-only branch does not modify `main` and is not an implementation branch.

Source R7 archive SHA256:

`cb856bde1d8d4723d51db08eb07a21a46704dd2c91510606cd5b610b2660f48a`

Transport bundle contents:

- `authority/**`
- `requirements/**`
- `test-matrix/**`
- `traceability/**`
- `CONTRACT_FILE_HASHES.sha256`

Transport bundle SHA256:

`def56ecc6274c995b587c24253acbb99ca2fd0dd517b2d2f5f28593905a75800`

Restore:

```bash
base64 -d TASK012-R7-CONTRACT-BASELINE.tar.gz.b64 > TASK012-R7-CONTRACT-BASELINE.tar.gz
sha256sum -c TASK012-R7-CONTRACT-BASELINE.tar.gz.sha256
tar -xzf TASK012-R7-CONTRACT-BASELINE.tar.gz
sha256sum -c CONTRACT_FILE_HASHES.sha256
```

Authorization remains unchanged:

```text
TASK012_SLICE1_AUTHORIZED=NO
TASK012_IMPLEMENTATION_AUTHORIZED=NO
PRODUCTION_DEPLOYMENT_AUTHORIZED=NO
```
