# Upload Test Fixtures

Files in this directory are used by the `/web-qa-runner` Playwright tests when running in `--depth full` mode.

Tests that upload these files will clean up after themselves (delete the uploaded file from the server).

## Files

- `QA-TEST.TXT` — minimal text file for single-file upload flow testing
