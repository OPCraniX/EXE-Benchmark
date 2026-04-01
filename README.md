# EXE Benchmark

`EXE Benchmark` is a Windows-focused Python utility for comparing two executables across repeated launches. It measures launch speed, CPU usage, memory usage, disk I/O, process-tree activity, and shutdown behavior, then saves a comparison chart as a PNG.

## What It Measures

- Launch time
- Startup CPU and memory usage
- After-start CPU and memory usage
- Peak memory usage
- Startup and total disk read/write volume
- Startup and total read/write operation counts
- Peak process count and helper-process count
- Unique processes observed across the full run
- Shutdown time and forced-kill count

## Requirements

- Windows 10 or Windows 11
- Python 3.8 or newer
- `psutil`
- `matplotlib`

Install dependencies with:

```powershell
python -m pip install psutil matplotlib
```

If your system uses the Python launcher instead of `python`, use:

```powershell
py -m pip install psutil matplotlib
```

## Quick Start

Compare two executables with the default 3 runs per app:

```powershell
python .\benchmark_exes.py `
  --exe1 "C:\Path\To\App-One.exe" `
  --exe2 "C:\Path\To\App-Two.exe" `
  --label1 "App One" `
  --label2 "App Two"
```

Save the chart with a custom filename and run five samples:

```powershell
python .\benchmark_exes.py `
  --exe1 "C:\Apps\BuildA.exe" `
  --exe2 "C:\Apps\BuildB.exe" `
  --label1 "Build A" `
  --label2 "Build B" `
  --runs 5 `
  --output "build-comparison.png"
```

Compare the same executable with different runtime arguments:

```powershell
python .\benchmark_exes.py `
  --exe1 "C:\Apps\Example.exe" `
  --exe2 "C:\Apps\Example.exe" `
  --label1 "Default" `
  --label2 "Portable Mode" `
  --args2 Portable `
  --runs 4
```

## Command-Line Options

| Option | Description | Default |
| --- | --- | --- |
| `--exe1` | Path to the first executable | Required |
| `--exe2` | Path to the second executable | Required |
| `--label1` | Display name for EXE 1 | `EXE 1` |
| `--label2` | Display name for EXE 2 | `EXE 2` |
| `--args1` | Extra arguments passed to EXE 1 | None |
| `--args2` | Extra arguments passed to EXE 2 | None |
| `--runs` | Number of runs per executable | `3` |
| `--startup-window` | Seconds treated as startup time | `5.0` |
| `--steady-window` | Seconds treated as after-start time | `5.0` |
| `--sample-interval` | Sampling interval in seconds | `0.2` |
| `--no-auto-terminate` | Leave the apps running after sampling | Off |
| `--output` | Output PNG filename | `exe_benchmark.png` |
| `--priority` | Windows priority class: `idle`, `below-normal`, `normal`, `above-normal`, `high`, or `realtime` | `normal` |

## Output

The script prints:

- Per-run details for each executable
- A fastest-to-slowest run ranking
- Aggregate summaries for both executables
- A quick winner snapshot across key categories
- Environment metadata including CPU, RAM, Windows version, file paths, and file versions

It also writes a PNG chart that includes:

- Average launch time
- CPU comparison
- Memory comparison
- CPU timeline for every run
- Detailed I/O, process, and shutdown metrics

## Notes

- The benchmark tracks the root process and its child processes, which helps when an EXE launches helper processes or hands work off to another process.
- Standard output and standard error from the tested executables are suppressed during benchmarking.
- With auto-termination enabled, the script attempts a graceful shutdown first and force-kills remaining processes if needed.
- `realtime` priority can make the system less responsive. Use it only on a dedicated test machine.
- Benchmarking GUI applications is easiest when the apps can reach a stable idle state without manual input.

## Suggested Workflow

1. Close background apps you do not need.
2. Benchmark both EXEs with the same number of runs.
3. Keep startup and steady-state windows identical for both sides.
4. Review the console summary first, then inspect the PNG for run-to-run consistency.
5. Repeat the test if antivirus scans, updates, or first-run setup skew a result.

## Troubleshooting

- `EXE not found`: confirm the path is correct and points to a real `.exe`.
- `Process exited immediately`: the executable may require extra arguments, a working directory, or user interaction.
- `Timed out waiting for process to become observable`: the process may start and exit too quickly or be blocked by security software.
- Priority warnings: some priority classes require elevated permissions or may be rejected by Windows.

See [HELP.md](./HELP.md) for a command reference and more troubleshooting guidance.
