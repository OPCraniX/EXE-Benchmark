# Security Policy

## Supported Versions

This repository is currently maintained as a single rolling code line.

| Version | Supported |
| --- | --- |
| Latest default branch | Yes |

## Reporting a Vulnerability

Please do not open a public issue for a suspected security problem.

Use one of these routes instead:

1. Use GitHub's private vulnerability reporting flow for this repository, if it is enabled.
2. If private reporting is not available, contact the maintainer through the [OPCraniX GitHub profile](https://github.com/OPCraniX) and include `EXE-Benchmark security report` in the message.

Please include:

- The affected commit, branch, or file
- Your Windows version and Python version
- The exact command used to reproduce the issue
- A short description of impact
- Screenshots, stack traces, or logs if available
- Whether a proof-of-concept executable is required to reproduce

You can expect acknowledgement as soon as the maintainer is available, followed by reproduction and remediation work when the report is confirmed.

## Scope

Security-relevant reports include issues such as:

- Unsafe execution or argument handling
- Unintended process termination outside the benchmarked process tree
- Path handling flaws
- Dependency vulnerabilities that materially affect repository users
- Documentation mistakes that could encourage unsafe execution practices

General bugs, charting issues, or inaccurate metrics should be reported as normal repository issues unless they have a real security impact.

## Safe Use Guidance

This project launches local executables provided by the user. Benchmarking a binary should be treated with the same caution as running it normally.

To reduce risk:

- Only benchmark trusted executables from known sources.
- Prefer a test machine, VM, or disposable environment for unknown or freshly built binaries.
- Avoid `realtime` priority unless you fully understand the stability impact on the host system.
- Do not post malware samples, proprietary binaries, license keys, or sensitive crash dumps in public issues.
- If a report needs a binary sample, share hashes or a minimal safe reproducer whenever possible.

## Dependency Hygiene

Keep local Python packages current and install dependencies from trusted sources. At minimum, review updates for:

- `psutil`
- `matplotlib`

If a dependency vulnerability affects this project, please report it through the private process above.
