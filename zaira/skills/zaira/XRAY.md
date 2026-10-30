---
updated: 2026-10-28
---
# Xray Cloud

Read Xray tests and record Test Run results. Needs a separate Xray Cloud API key: run `zaira init-xray` once (Jira credentials from `zaira init` are not enough).

## Read tests

```bash
zaira get FOO-1234 --with-tests             # Ticket plus linked tests, executions, steps
zaira xray get FOO-1234                     # Test as standalone markdown (stdout)
zaira xray get FOO-1234 FOO-5678 -o tests/  # One KEY.md per test
```

## Edit test steps

Change the manual steps (Action, Data, Expected Result) of the Test itself, as opposed to recording run results. All accept `--dry-run`. Step numbers are 1-based positions as shown by `xray get`.

```bash
zaira xray step-add FOO-10 --action "Click Save" --result "Toast appears" --data "name=x"
zaira xray step-edit FOO-10 --step 2 --result "Toast says Saved"   # only given fields change
zaira xray step-rm FOO-10 --step 3
zaira xray step-attach FOO-10 --step 2 shot.png log.txt   # add files to a step

# Replace ALL steps from the markdown steps table (round-trips with `xray get`)
zaira xray get FOO-10 -o tests/       # edit the table in tests/FOO-10.md
zaira xray steps-put FOO-10 tests/FOO-10.md --dry-run
zaira xray steps-put FOO-10 tests/FOO-10.md
```

`step-add` appends at the end; there is no insert-at-position. `steps-put` deletes every existing step and re-adds the table rows, so step ids change and attachments on old steps are lost; use `step-edit` for small changes. Only Manual (Steps) tests have steps; Cucumber and Generic definitions are not editable.

## Record results

A Test Run is one Test inside one Test Execution, so every write command takes `--exec TE-KEY`. All write commands accept `--dry-run` (show what would change, send nothing). Keys are case-insensitive.

```bash
# Create an execution for a set of tests (prints the new key)
zaira xray exec-create --project FOO --summary "Release 1.2 regression" \
    --tests FOO-10 FOO-11 FOO-12 --env chrome --env firefox

# Set overall status of one or more tests
zaira xray run-status FOO-10 FOO-11 --exec FOO-99 --status PASSED

# Set one step (1-based position, not step id); give any of status/actual/comment
zaira xray run-step FOO-10 --exec FOO-99 --step 2 --status FAILED \
    --actual "500 on submit" --comment "see log"

# Apply many results from a JSON file
zaira xray run-import results.json --exec FOO-99
```

Statuses are Xray status names, e.g. `PASSED`, `FAILED`, `TODO`, `EXECUTING`. `--env` is repeatable.

### run-import file format

A JSON list. `status` and `steps` are both optional per entry; step fields other than `n` are optional.

```json
[
  {
    "test": "FOO-10",
    "status": "FAILED",
    "steps": [
      {"n": 1, "status": "PASSED"},
      {"n": 2, "status": "FAILED", "actual": "500 on submit", "comment": "see log"}
    ]
  },
  {"test": "FOO-11", "status": "PASSED"}
]
```

Failures are reported per test on stderr and the command exits 1 after trying the rest, so a partial import can be re-run safely (writes set absolute values).
