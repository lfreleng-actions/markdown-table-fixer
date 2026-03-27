<!--
SPDX-License-Identifier: Apache-2.0
SPDX-FileCopyrightText: 2025 The Linux Foundation
-->

# Example Document with Bad Tables

This document contains examples of incorrectly formatted markdown tables that
markdown-table-fixer can detect and fix.

## Example 1: Missing Spaces

| Name | Type   | Description   |
| ---- | ------ | ------------- |
| foo  | string | A value       |
| bar  | int    | Another value |

## Example 2: Misaligned Pipes

| Name   | Required | Description   |
| ------ | -------- | ------------- |
| input  | False    | Action input  |
| output | True     | Action output |

## Example 3: Inconsistent Spacing

| Flag     | Short | Default | Description                      |
| -------- | ----- | ------- | -------------------------------- |
| --path   | -p    | "."     | Path to search for project files |
| --config | -c    | ""      | Path to configuration file       |
| --format | -f    | "text"  | Output format: text, json        |

## Example 4: Mixed Issues

| Col1 | Col2 | Col3 |
| ---- | ---- | ---- |
| A    | B    | C    |
| D    | E    | F    |

## Example 5: Common Emojis - Status Indicators

| Feature        | Status | Priority | Notes        |
| -------------- | ------ | -------- | ------------ |
| Authentication | ✅      | High     | Complete     |
| Authorization  | ❌      | High     | Not started  |
| Database       | ☑️     | Medium   | In progress  |
| API            | ⚠️     | High     | Needs review |
| Tests          | ✓      | Low      | Partial      |
| Deploy         | ✗      | Medium   | Blocked      |

## Example 6: Emojis with Misaligned Pipes

| Task        | Done | Severity   |
| ----------- | ---- | ---------- |
| Fix bug     | ✅    | 🔴 Critical |
| Add tests   | ❌    | 🟢 Low      |
| Review code | ☑️   | 🟡 Medium   |

## Example 7: Unicode and Emoji Mix

| Symbol | Meaning       | Category      | Example Use                 |
| ------ | ------------- | ------------- | --------------------------- |
| ✅      | Checkmark     | Success       | Task completed successfully |
| ❌      | Cross         | Error         | Operation failed            |
| ⚠️     | Warning       | Alert         | Deprecated feature          |
| ☑️     | Checkbox      | Status        | Partially complete          |
| ✓      | Check         | Confirmed     | Verified result             |
| ✗      | X Mark        | Rejected      | Invalid input               |
| 🔴      | Red Circle    | Critical      | Production outage           |
| 🟢      | Green Circle  | Healthy       | All systems operational     |
| 🟡      | Yellow Circle | Warning       | High memory usage           |
| 🔵      | Blue Circle   | Info          | New feature available       |
| ⭐      | Star          | Important     | Featured item               |
| 🚀      | Rocket        | Launch        | Deployment ready            |
| 🐛      | Bug           | Issue         | Known defect                |
| 📝      | Memo          | Documentation | Needs docs update           |

## Example 8: Mixed Width Characters

| ID  | Status      | Description     | Owner     |
| --- | ----------- | --------------- | --------- |
| 1   | ✅ Done      | Fix parsing bug | 👤 Alice   |
| 2   | ❌ Failed    | Add new feature | 👤 Bob     |
| 3   | ⚠️ Warning  | Update docs     | 👤 Charlie |
| 4   | ☑️ Progress | Review PR       | 👤 David   |
