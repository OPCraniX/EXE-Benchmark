# EXE Benchmark Help

This file is a quick-reference guide for running `benchmark_exes.py`.

## Basic Usage

```powershell
python .\benchmark_exes.py --exe1 "C:\Path\To\AppA.exe" --exe2 "C:\Path\To\AppB.exe"
```

## Common Commands

Basic comparison with labels:

```powershell
python .\benchmark_exes.py `
  --exe1 "C:\Apps\AppA.exe" `
  --exe2 "C:\Apps\AppB.exe" `
  --label1 "App A" `
  --label2 "App B"
```

Run more samples for steadier averages:

```powershell
python .\benchmark_exes.py `
  --exe1 "C:\Apps\AppA.exe" `
  --exe2 "C:\Apps\AppB.exe" `
  --runs 7
```

Change the startup and steady-state windows:

```powershell
python .\benchmark_exes.py `
  --exe1 "C:\Apps\AppA.exe" `
  --exe2 "C:\Apps\AppB.exe" `
  --startup-window 3 `
  --steady-window 12
```

Save the output chart to a custom file:

```powershell
python .\benchmark_exes.py `
  --exe1 "C:\Apps\AppA.exe" `
  --exe2 "C:\Apps\AppB.exe" `
  --output "results\app-comparison.png"
```

Leave both applications running after the benchmark window finishes:

```powershell
python .\benchmark_exes.py `
  --exe1 "C:\Apps\AppA.exe" `
  --exe2 "C:\Apps\AppB.exe" `
  --no-auto-terminate
```

Change process priority:

```powershell
python .\benchmark_exes.py `
  --exe1 "C:\Apps\AppA.exe" `
  --exe2 "C:\Apps\AppB.exe" `
  --priority above-normal
```

Compare one EXE with different arguments:

```powershell
python .\benchmark_exes.py `
  --exe1 "C:\Apps\Example.exe" `
  --exe2 "C:\Apps\Example.exe" `
  --label1 "Default" `
  --label2 "Alt Config" `
  --args2 ConfigB
```

## Option Reference

| Option | Meaning |
| --- | --- |
| `--exe1` | Path to the first executable |
| `--exe2` | Path to the second executable |
| `--label1` | Friendly label shown in output for EXE 1 |
| `--label2` | Friendly label shown in output for EXE 2 |
| `--args1` | Zero or more arguments passed to EXE 1 |
| `--args2` | Zero or more arguments passed to EXE 2 |
| `--runs` | Number of benchmark runs per executable |
| `--startup-window` | Seconds included in the startup sampling window |
| `--steady-window` | Seconds included in the after-start sampling window |
| `--sample-interval` | Seconds between samples |
| `--no-auto-terminate` | Prevents the script from closing the launched apps |
| `--output` | PNG filename to write at the end of the benchmark |
| `--priority` | Process priority class for launched executables |

## Reading the Results

- Lower launch time means the executable becomes observable faster.
- Lower startup memory and CPU usually indicate a lighter first-run cost.
- Lower steady-state memory and CPU are useful for apps that stay open.
- Peak process and helper-process counts show how much background activity the EXE spawns.
- Shutdown time and forced-kill counts help identify apps that do not close cleanly.

## Troubleshooting

`python` command not found

- Use the full path to Python, or try `py` if the Python launcher is installed.

`EXE not found`

- Double-check the full path.
- Make sure you are pointing to the executable itself, not a shortcut.

`Process exited immediately with code ...`

- The EXE may need command-line arguments, a config file, or a specific working directory.
- Try launching it manually first to confirm it starts normally.

`Timed out waiting for process to become observable`

- Security software may be delaying startup.
- The EXE may be a short-lived wrapper that immediately exits.

Priority warning or access denied

- Some priority classes need elevated rights.
- Use `normal` or `above-normal` unless you have a controlled test machine.

Results look noisy

- Close browsers, updaters, game launchers, and background sync tools.
- Increase `--runs` and compare averages instead of single runs.
- Repeat the test after first-run setup or caching effects have settled.

No meaningful shutdown data

- If you used `--no-auto-terminate`, shutdown timing is expected to be limited.
- Some applications keep helper processes alive after the main window closes.

## Safe Benchmarking Tips

- Only benchmark executables you trust.
- Test one pair of apps at a time.
- Keep both apps on the same storage device when possible.
- Avoid changing antivirus, power plan, or thermal conditions mid-test.
- Be cautious with `realtime` priority.
