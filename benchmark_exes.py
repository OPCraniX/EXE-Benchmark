import argparse
import ctypes
import os
import platform
import statistics
import subprocess
import time
from ctypes import wintypes
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple

try:
    import winreg
except ImportError:
    winreg = None

import matplotlib.pyplot as plt
import psutil
from matplotlib.lines import Line2D


# ============================================================
# CONFIG / DATA STRUCTURES
# ============================================================

@dataclass
class RunMetrics:
    launch_time_sec: float
    startup_avg_cpu_percent: float
    startup_avg_mem_mb: float
    steady_avg_cpu_percent: float
    steady_avg_mem_mb: float
    peak_mem_mb: float
    startup_read_bytes_mb: float
    startup_write_bytes_mb: float
    startup_read_count: int
    startup_write_count: int
    total_read_bytes_mb: float
    total_write_bytes_mb: float
    total_read_count: int
    total_write_count: int
    peak_process_count: int
    peak_child_process_count: int
    unique_process_count: int
    unique_child_process_count: int
    shutdown_time_sec: float
    force_killed_processes: int
    samples_time: List[float]
    samples_cpu: List[float]
    samples_mem_mb: List[float]
    exited_early: bool
    exit_code: Optional[int]


@dataclass
class AggregateMetrics:
    label: str
    exe_path: str
    runs: int
    launch_time_sec_avg: float
    launch_time_sec_min: float
    launch_time_sec_max: float
    startup_avg_cpu_percent: float
    startup_avg_mem_mb: float
    steady_avg_cpu_percent: float
    steady_avg_mem_mb: float
    peak_mem_mb: float
    startup_read_bytes_mb: float
    startup_write_bytes_mb: float
    startup_read_count: float
    startup_write_count: float
    total_read_bytes_mb: float
    total_write_bytes_mb: float
    total_read_count: float
    total_write_count: float
    peak_process_count: float
    peak_child_process_count: float
    unique_process_count: float
    unique_child_process_count: float
    shutdown_time_sec_avg: float
    force_killed_processes_avg: float


@dataclass
class ProcessSnapshot:
    cpu_percent: float
    mem_mb: float
    read_bytes: int
    write_bytes: int
    read_count: int
    write_count: int
    process_count: int
    child_process_count: int


@dataclass
class TerminationResult:
    exit_code: Optional[int]
    shutdown_time_sec: float
    force_killed_processes: int


@dataclass
class ExecutableInfo:
    label: str
    path: str
    filename: str
    file_version: str


@dataclass
class BenchmarkContext:
    run_timestamp: str
    cpu_name: str
    total_ram_gb: float
    windows_version: str
    exe1: ExecutableInfo
    exe2: ExecutableInfo
    runs_per_exe: int


# ============================================================
# HELPERS
# ============================================================

def bytes_to_mb(value: int) -> float:
    return value / (1024 * 1024)


def safe_mean(values: List[float]) -> float:
    return statistics.mean(values) if values else 0.0


def safe_min(values: List[float]) -> float:
    return min(values) if values else 0.0


def safe_max(values: List[float]) -> float:
    return max(values) if values else 0.0


class VS_FIXEDFILEINFO(ctypes.Structure):
    _fields_ = [
        ("dwSignature", wintypes.DWORD),
        ("dwStrucVersion", wintypes.DWORD),
        ("dwFileVersionMS", wintypes.DWORD),
        ("dwFileVersionLS", wintypes.DWORD),
        ("dwProductVersionMS", wintypes.DWORD),
        ("dwProductVersionLS", wintypes.DWORD),
        ("dwFileFlagsMask", wintypes.DWORD),
        ("dwFileFlags", wintypes.DWORD),
        ("dwFileOS", wintypes.DWORD),
        ("dwFileType", wintypes.DWORD),
        ("dwFileSubtype", wintypes.DWORD),
        ("dwFileDateMS", wintypes.DWORD),
        ("dwFileDateLS", wintypes.DWORD),
    ]


def hiword(value: int) -> int:
    return value >> 16


def loword(value: int) -> int:
    return value & 0xFFFF


def get_registry_value(root: int, path: str, name: str) -> Optional[str]:
    if winreg is None:
        return None

    try:
        with winreg.OpenKey(root, path) as key:
            value, _ = winreg.QueryValueEx(key, name)
        if isinstance(value, str):
            return " ".join(value.split())
        return str(value)
    except OSError:
        return None


def get_cpu_name() -> str:
    cpu_name = get_registry_value(
        getattr(winreg, "HKEY_LOCAL_MACHINE", 0),
        r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
        "ProcessorNameString",
    )
    if cpu_name:
        return cpu_name

    cpu_name = platform.processor().strip()
    return cpu_name or "Unknown CPU"


def get_windows_version() -> str:
    product_name = get_registry_value(
        getattr(winreg, "HKEY_LOCAL_MACHINE", 0),
        r"SOFTWARE\Microsoft\Windows NT\CurrentVersion",
        "ProductName",
    )
    display_version = get_registry_value(
        getattr(winreg, "HKEY_LOCAL_MACHINE", 0),
        r"SOFTWARE\Microsoft\Windows NT\CurrentVersion",
        "DisplayVersion",
    )
    current_build = get_registry_value(
        getattr(winreg, "HKEY_LOCAL_MACHINE", 0),
        r"SOFTWARE\Microsoft\Windows NT\CurrentVersion",
        "CurrentBuild",
    )
    ubr = get_registry_value(
        getattr(winreg, "HKEY_LOCAL_MACHINE", 0),
        r"SOFTWARE\Microsoft\Windows NT\CurrentVersion",
        "UBR",
    )
    edition_id = get_registry_value(
        getattr(winreg, "HKEY_LOCAL_MACHINE", 0),
        r"SOFTWARE\Microsoft\Windows NT\CurrentVersion",
        "EditionID",
    )

    friendly_product_name = product_name
    try:
        build_number = int(current_build) if current_build else 0
    except ValueError:
        build_number = 0

    if not friendly_product_name and edition_id:
        friendly_product_name = f"Windows {edition_id}"

    # Windows 11 commonly still reports "Windows 10" in this registry value.
    if friendly_product_name and friendly_product_name.startswith("Windows 10") and build_number >= 22000:
        friendly_product_name = friendly_product_name.replace("Windows 10", "Windows 11", 1)

    architecture = platform.machine().upper()
    if architecture in {"AMD64", "X86_64"}:
        architecture = "x64"
    elif architecture == "ARM64":
        architecture = "ARM64"

    build_label = None
    if current_build and ubr:
        build_label = f"Build {current_build}.{ubr}"
    elif current_build:
        build_label = f"Build {current_build}"

    pieces = [piece for piece in [friendly_product_name, display_version, build_label, architecture] if piece]
    if pieces:
        return " | ".join(pieces)

    return platform.platform(aliased=True)


def get_file_version(file_path: str) -> str:
    if os.name != "nt" or not os.path.isfile(file_path):
        return "Unavailable"

    try:
        size = ctypes.windll.version.GetFileVersionInfoSizeW(file_path, None)
        if not size:
            return "Unavailable"

        buffer = ctypes.create_string_buffer(size)
        if not ctypes.windll.version.GetFileVersionInfoW(file_path, 0, size, buffer):
            return "Unavailable"

        value_ptr = ctypes.c_void_p()
        value_len = wintypes.UINT()
        if not ctypes.windll.version.VerQueryValueW(
            buffer,
            "\\",
            ctypes.byref(value_ptr),
            ctypes.byref(value_len),
        ):
            return "Unavailable"

        file_info = ctypes.cast(value_ptr, ctypes.POINTER(VS_FIXEDFILEINFO)).contents
        if file_info.dwSignature != 0xFEEF04BD:
            return "Unavailable"

        return (
            f"{hiword(file_info.dwFileVersionMS)}."
            f"{loword(file_info.dwFileVersionMS)}."
            f"{hiword(file_info.dwFileVersionLS)}."
            f"{loword(file_info.dwFileVersionLS)}"
        )
    except Exception:
        return "Unavailable"


def build_benchmark_context(
    exe1_path: str,
    exe2_path: str,
    label1: str,
    label2: str,
    runs: int,
) -> BenchmarkContext:
    exe1_abs = os.path.abspath(exe1_path)
    exe2_abs = os.path.abspath(exe2_path)

    return BenchmarkContext(
        run_timestamp=datetime.now().astimezone().strftime("%Y-%m-%d %I:%M:%S %p %Z"),
        cpu_name=get_cpu_name(),
        total_ram_gb=psutil.virtual_memory().total / (1024 ** 3),
        windows_version=get_windows_version(),
        exe1=ExecutableInfo(
            label=label1,
            path=exe1_abs,
            filename=os.path.basename(exe1_abs),
            file_version=get_file_version(exe1_abs),
        ),
        exe2=ExecutableInfo(
            label=label2,
            path=exe2_abs,
            filename=os.path.basename(exe2_abs),
            file_version=get_file_version(exe2_abs),
        ),
        runs_per_exe=runs,
    )


def get_process_tree(root_proc: psutil.Process, tracked_pids: Optional[Set[int]] = None) -> List[psutil.Process]:
    """
    Return the root process, any tracked descendants, and all of their children,
    ignoring dead processes. This helps keep helper processes in the benchmark
    even if the original root PID exits.
    """
    seeds = []
    try:
        if root_proc.is_running():
            seeds.append(root_proc)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass

    if tracked_pids:
        for pid in tracked_pids:
            if pid == root_proc.pid:
                continue
            try:
                proc = psutil.Process(pid)
                if proc.is_running():
                    seeds.append(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

    alive = []
    seen = set()
    for p in seeds:
        try:
            if p.pid not in seen and p.is_running():
                alive.append(p)
                seen.add(p.pid)
                for child in p.children(recursive=True):
                    if child.pid not in seen and child.is_running():
                        alive.append(child)
                        seen.add(child.pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    return alive


def prime_cpu_counters(procs: List[psutil.Process], primed: set) -> None:
    """
    psutil cpu_percent(None) needs one warm-up call before meaningful values appear.
    """
    for p in procs:
        if p.pid not in primed:
            try:
                p.cpu_percent(interval=None)
                primed.add(p.pid)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue


def sample_tree_usage(
    root_proc: psutil.Process,
    primed: set,
    io_tracker: Dict[int, Tuple[int, int, int, int]],
    tracked_pids: Set[int],
) -> ProcessSnapshot:
    """
    Returns current CPU/memory plus I/O deltas since the previous sample
    for the root process and all children.
    """
    procs = get_process_tree(root_proc, tracked_pids)
    prime_cpu_counters(procs, primed)

    total_cpu = 0.0
    total_mem_mb = 0.0
    read_bytes_delta = 0
    write_bytes_delta = 0
    read_count_delta = 0
    write_count_delta = 0

    for p in procs:
        tracked_pids.add(p.pid)

        try:
            total_cpu += p.cpu_percent(interval=None)
            total_mem_mb += bytes_to_mb(p.memory_info().rss)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

        try:
            io = p.io_counters()
            current_io = (io.read_bytes, io.write_bytes, io.read_count, io.write_count)
            previous_io = io_tracker.get(p.pid)
            if previous_io is None:
                delta = current_io
            else:
                delta = tuple(max(0, curr - prev) for curr, prev in zip(current_io, previous_io))

            read_bytes_delta += delta[0]
            write_bytes_delta += delta[1]
            read_count_delta += delta[2]
            write_count_delta += delta[3]
            io_tracker[p.pid] = current_io
        except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError):
            continue

    return ProcessSnapshot(
        cpu_percent=total_cpu,
        mem_mb=total_mem_mb,
        read_bytes=read_bytes_delta,
        write_bytes=write_bytes_delta,
        read_count=read_count_delta,
        write_count=write_count_delta,
        process_count=len(procs),
        child_process_count=sum(1 for p in procs if p.pid != root_proc.pid),
    )


def terminate_process_tree(
    root_proc: psutil.Process,
    tracked_pids: Optional[Set[int]] = None,
    timeout: float = 5.0,
) -> TerminationResult:
    """
    Gracefully terminates the process tree, then force kills if needed.
    """
    shutdown_start = time.perf_counter()
    force_killed_processes = 0

    try:
        procs = get_process_tree(root_proc, tracked_pids)
        for p in reversed(procs):
            try:
                p.terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        _, alive = psutil.wait_procs(procs, timeout=timeout)
        force_killed_processes = len(alive)

        for p in alive:
            try:
                p.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        if alive:
            psutil.wait_procs(alive, timeout=timeout)

        try:
            exit_code = root_proc.wait(timeout=1)
        except (psutil.TimeoutExpired, psutil.NoSuchProcess):
            exit_code = None

    except (psutil.NoSuchProcess, psutil.AccessDenied):
        exit_code = None

    return TerminationResult(
        exit_code=exit_code,
        shutdown_time_sec=time.perf_counter() - shutdown_start,
        force_killed_processes=force_killed_processes,
    )


def wait_for_process_start(popen_obj: subprocess.Popen, timeout: float = 10.0) -> Tuple[psutil.Process, float]:
    """
    Wait until the process is observable via psutil.
    """
    start = time.perf_counter()
    deadline = start + timeout

    while time.perf_counter() < deadline:
        if popen_obj.poll() is not None:
            raise RuntimeError(f"Process exited immediately with code {popen_obj.returncode}")

        try:
            proc = psutil.Process(popen_obj.pid)
            _ = proc.status()
            launch_time = time.perf_counter() - start
            return proc, launch_time
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            time.sleep(0.01)

    raise TimeoutError("Timed out waiting for process to become observable")


def get_priority_class(priority_name: str) -> Optional[int]:
    """
    Map a friendly priority name to a Windows psutil priority class.
    Returns None if normal/default should be used or if not supported.
    """
    priority_name = priority_name.lower().strip()

    mapping = {
        "idle": getattr(psutil, "IDLE_PRIORITY_CLASS", None),
        "below-normal": getattr(psutil, "BELOW_NORMAL_PRIORITY_CLASS", None),
        "normal": getattr(psutil, "NORMAL_PRIORITY_CLASS", None),
        "above-normal": getattr(psutil, "ABOVE_NORMAL_PRIORITY_CLASS", None),
        "high": getattr(psutil, "HIGH_PRIORITY_CLASS", None),
        "realtime": getattr(psutil, "REALTIME_PRIORITY_CLASS", None),
    }

    return mapping.get(priority_name)


def apply_process_priority(proc: psutil.Process, priority_name: str) -> None:
    """
    Apply the requested process priority on Windows.
    Silently skips unsupported environments.
    """
    if os.name != "nt":
        print(f"[INFO] Priority '{priority_name}' requested, but priority classes are only applied on Windows.")
        return

    priority_class = get_priority_class(priority_name)
    if priority_class is None:
        print(f"[WARNING] Unsupported priority '{priority_name}', using system default.")
        return

    try:
        proc.nice(priority_class)
        print(f"[INFO] Applied priority: {priority_name}")
    except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
        print(f"[WARNING] Failed to set priority '{priority_name}': {e}")


# ============================================================
# CORE BENCHMARK
# ============================================================

def benchmark_exe_once(
    exe_path: str,
    args: List[str],
    startup_window: float,
    steady_window: float,
    sample_interval: float,
    auto_terminate: bool,
    priority: str = "normal",
    cwd: Optional[str] = None
) -> RunMetrics:
    if not os.path.isfile(exe_path):
        raise FileNotFoundError(f"EXE not found: {exe_path}")

    command = [exe_path] + args

    popen = subprocess.Popen(
        command,
        cwd=cwd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    proc, launch_time = wait_for_process_start(popen)
    primed = set()
    io_tracker: Dict[int, Tuple[int, int, int, int]] = {}
    tracked_pids: Set[int] = {proc.pid}

    # Apply requested process priority after the process becomes observable
    apply_process_priority(proc, priority)

    # Prime CPU counters once before timed sampling begins
    initial_tree = get_process_tree(proc, tracked_pids)
    tracked_pids.update(p.pid for p in initial_tree)
    prime_cpu_counters(initial_tree, primed)
    time.sleep(sample_interval)

    total_window = startup_window + steady_window
    start_t = time.perf_counter()

    samples_time: List[float] = []
    samples_cpu: List[float] = []
    samples_mem_mb: List[float] = []
    startup_cpu: List[float] = []
    startup_mem: List[float] = []
    steady_cpu: List[float] = []
    steady_mem: List[float] = []

    exited_early = False
    exit_code = None
    startup_read_bytes = 0
    startup_write_bytes = 0
    startup_read_count = 0
    startup_write_count = 0
    total_read_bytes = 0
    total_write_bytes = 0
    total_read_count = 0
    total_write_count = 0
    peak_process_count = len(initial_tree)
    peak_child_process_count = max(0, len(initial_tree) - 1)
    shutdown_time_sec = 0.0
    force_killed_processes = 0

    while True:
        now = time.perf_counter()
        elapsed = now - start_t

        if elapsed >= total_window:
            break

        snapshot = sample_tree_usage(proc, primed, io_tracker, tracked_pids)
        if snapshot.process_count == 0:
            exited_early = True
            exit_code = popen.returncode
            break

        samples_time.append(elapsed)
        samples_cpu.append(snapshot.cpu_percent)
        samples_mem_mb.append(snapshot.mem_mb)

        if elapsed <= startup_window:
            startup_cpu.append(snapshot.cpu_percent)
            startup_mem.append(snapshot.mem_mb)
            startup_read_bytes += snapshot.read_bytes
            startup_write_bytes += snapshot.write_bytes
            startup_read_count += snapshot.read_count
            startup_write_count += snapshot.write_count
        else:
            steady_cpu.append(snapshot.cpu_percent)
            steady_mem.append(snapshot.mem_mb)

        total_read_bytes += snapshot.read_bytes
        total_write_bytes += snapshot.write_bytes
        total_read_count += snapshot.read_count
        total_write_count += snapshot.write_count
        peak_process_count = max(peak_process_count, snapshot.process_count)
        peak_child_process_count = max(peak_child_process_count, snapshot.child_process_count)

        time.sleep(sample_interval)

    if auto_terminate and get_process_tree(proc, tracked_pids):
        termination = terminate_process_tree(proc, tracked_pids)
        exit_code = termination.exit_code
        shutdown_time_sec = termination.shutdown_time_sec
        force_killed_processes = termination.force_killed_processes
        if exit_code is None and popen.poll() is not None:
            exit_code = popen.returncode
    elif popen.poll() is not None:
        exit_code = popen.returncode

    peak_mem = safe_max(samples_mem_mb)

    return RunMetrics(
        launch_time_sec=launch_time,
        startup_avg_cpu_percent=safe_mean(startup_cpu),
        startup_avg_mem_mb=safe_mean(startup_mem),
        steady_avg_cpu_percent=safe_mean(steady_cpu),
        steady_avg_mem_mb=safe_mean(steady_mem),
        peak_mem_mb=peak_mem,
        startup_read_bytes_mb=bytes_to_mb(startup_read_bytes),
        startup_write_bytes_mb=bytes_to_mb(startup_write_bytes),
        startup_read_count=startup_read_count,
        startup_write_count=startup_write_count,
        total_read_bytes_mb=bytes_to_mb(total_read_bytes),
        total_write_bytes_mb=bytes_to_mb(total_write_bytes),
        total_read_count=total_read_count,
        total_write_count=total_write_count,
        peak_process_count=peak_process_count,
        peak_child_process_count=peak_child_process_count,
        unique_process_count=len(tracked_pids),
        unique_child_process_count=max(0, len(tracked_pids - {proc.pid})),
        shutdown_time_sec=shutdown_time_sec,
        force_killed_processes=force_killed_processes,
        samples_time=samples_time,
        samples_cpu=samples_cpu,
        samples_mem_mb=samples_mem_mb,
        exited_early=exited_early,
        exit_code=exit_code
    )


def aggregate_runs(label: str, exe_path: str, run_metrics: List[RunMetrics]) -> AggregateMetrics:
    return AggregateMetrics(
        label=label,
        exe_path=exe_path,
        runs=len(run_metrics),
        launch_time_sec_avg=safe_mean([r.launch_time_sec for r in run_metrics]),
        launch_time_sec_min=safe_min([r.launch_time_sec for r in run_metrics]),
        launch_time_sec_max=safe_max([r.launch_time_sec for r in run_metrics]),
        startup_avg_cpu_percent=safe_mean([r.startup_avg_cpu_percent for r in run_metrics]),
        startup_avg_mem_mb=safe_mean([r.startup_avg_mem_mb for r in run_metrics]),
        steady_avg_cpu_percent=safe_mean([r.steady_avg_cpu_percent for r in run_metrics]),
        steady_avg_mem_mb=safe_mean([r.steady_avg_mem_mb for r in run_metrics]),
        peak_mem_mb=safe_mean([r.peak_mem_mb for r in run_metrics]),
        startup_read_bytes_mb=safe_mean([r.startup_read_bytes_mb for r in run_metrics]),
        startup_write_bytes_mb=safe_mean([r.startup_write_bytes_mb for r in run_metrics]),
        startup_read_count=safe_mean([r.startup_read_count for r in run_metrics]),
        startup_write_count=safe_mean([r.startup_write_count for r in run_metrics]),
        total_read_bytes_mb=safe_mean([r.total_read_bytes_mb for r in run_metrics]),
        total_write_bytes_mb=safe_mean([r.total_write_bytes_mb for r in run_metrics]),
        total_read_count=safe_mean([r.total_read_count for r in run_metrics]),
        total_write_count=safe_mean([r.total_write_count for r in run_metrics]),
        peak_process_count=safe_mean([r.peak_process_count for r in run_metrics]),
        peak_child_process_count=safe_mean([r.peak_child_process_count for r in run_metrics]),
        unique_process_count=safe_mean([r.unique_process_count for r in run_metrics]),
        unique_child_process_count=safe_mean([r.unique_child_process_count for r in run_metrics]),
        shutdown_time_sec_avg=safe_mean([r.shutdown_time_sec for r in run_metrics]),
        force_killed_processes_avg=safe_mean([r.force_killed_processes for r in run_metrics]),
    )


# ============================================================
# PLOTTING
# ============================================================

def plot_comparison(
    agg1: AggregateMetrics,
    agg2: AggregateMetrics,
    runs1: List[RunMetrics],
    runs2: List[RunMetrics],
    context: BenchmarkContext,
    output_png: str
) -> None:
    def build_metrics_block(agg: AggregateMetrics) -> str:
        return "\n".join([
            f"Startup disk read/write: {agg.startup_read_bytes_mb:.2f} / {agg.startup_write_bytes_mb:.2f} MB",
            f"Startup read/write ops: {agg.startup_read_count:.0f} / {agg.startup_write_count:.0f}",
            f"Total disk read/write:   {agg.total_read_bytes_mb:.2f} / {agg.total_write_bytes_mb:.2f} MB",
            f"Total read/write ops:    {agg.total_read_count:.0f} / {agg.total_write_count:.0f}",
            f"Peak process count:      {agg.peak_process_count:.2f}",
            f"Peak child processes:    {agg.peak_child_process_count:.2f}",
            f"Unique processes seen:   {agg.unique_process_count:.2f}",
            f"Unique child processes:  {agg.unique_child_process_count:.2f}",
            f"Avg shutdown time:       {agg.shutdown_time_sec_avg:.4f} sec",
            f"Avg force-killed procs:  {agg.force_killed_processes_avg:.2f}",
        ])

    def style_panel(panel, edge_color: str, face_color: str) -> None:
        panel.set_facecolor(face_color)
        panel.set_xticks([])
        panel.set_yticks([])
        for spine in panel.spines.values():
            spine.set_visible(True)
            spine.set_edgecolor(edge_color)
            spine.set_linewidth(1.2)

    exe1_color = "lightskyblue"
    exe2_color = "orange"
    fig, axes = plt.subplots(2, 2, figsize=(16, 15))
    fig.suptitle("EXE Benchmark Comparison", fontsize=16, fontweight="bold")

    labels = [agg1.label, agg2.label]

    # Chart 1: launch time
    axes[0, 0].bar(
        labels,
        [agg1.launch_time_sec_avg, agg2.launch_time_sec_avg],
        color=[exe1_color, exe2_color]
    )
    axes[0, 0].set_title("Average Launch Time")
    axes[0, 0].set_ylabel("Seconds")

    # Chart 2: startup CPU / steady CPU
    x = [0, 1]
    width = 0.35
    axes[0, 1].bar(
        [i - width / 2 for i in x],
        [agg1.startup_avg_cpu_percent, agg2.startup_avg_cpu_percent],
        width=width,
        color=[exe1_color, exe2_color],
        label="Startup CPU"
    )
    axes[0, 1].bar(
        [i + width / 2 for i in x],
        [agg1.steady_avg_cpu_percent, agg2.steady_avg_cpu_percent],
        width=width,
        color=[exe1_color, exe2_color],
        label="After Start CPU"
    )
    axes[0, 1].set_xticks(x)
    axes[0, 1].set_xticklabels(labels)
    axes[0, 1].set_title("CPU Usage Comparison")
    axes[0, 1].set_ylabel("CPU %")
    axes[0, 1].legend()

    # Chart 3: startup memory / steady memory
    axes[1, 0].bar(
        [i - width / 2 for i in x],
        [agg1.startup_avg_mem_mb, agg2.startup_avg_mem_mb],
        width=width,
        color=[exe1_color, exe2_color],
        label="Startup Memory"
    )
    axes[1, 0].bar(
        [i + width / 2 for i in x],
        [agg1.steady_avg_mem_mb, agg2.steady_avg_mem_mb],
        width=width,
        color=[exe1_color, exe2_color],
        label="After Start Memory"
    )
    axes[1, 0].set_xticks(x)
    axes[1, 0].set_xticklabels(labels)
    axes[1, 0].set_title("Memory Usage Comparison")
    axes[1, 0].set_ylabel("Memory (MB)")
    axes[1, 0].legend()

    # Chart 4: each run as its own line (CPU timeline)
    # EXE 1 = LIGHT BLUE
    for i, r in enumerate(runs1, start=1):
        if r.samples_time and r.samples_cpu:
            axes[1, 1].plot(
                r.samples_time,
                r.samples_cpu,
                color=exe1_color,
                alpha=0.7,
                linewidth=1.5
            )

    # EXE 2 = ORANGE
    for i, r in enumerate(runs2, start=1):
        if r.samples_time and r.samples_cpu:
            axes[1, 1].plot(
                r.samples_time,
                r.samples_cpu,
                color=exe2_color,
                alpha=0.7,
                linewidth=1.5
            )

    axes[1, 1].set_title("CPU Timeline - Each Run")
    axes[1, 1].set_xlabel("Seconds")
    axes[1, 1].set_ylabel("CPU %")
    axes[1, 1].legend(handles=[
        Line2D([0], [0], color=exe1_color, lw=2, label=agg1.label),
        Line2D([0], [0], color=exe2_color, lw=2, label=agg2.label),
    ], fontsize=8)

    footer_line_1 = (
        f"Run: {context.run_timestamp} | CPU: {context.cpu_name} | "
        f"RAM: {context.total_ram_gb:.1f} GB | Windows: {context.windows_version}"
    )
    exe_path_line_1 = f"EXE 1 Path: {context.exe1.path}"
    exe_path_line_2 = f"EXE 2 Path: {context.exe2.path}"

    metrics_block_1 = build_metrics_block(agg1)
    metrics_block_2 = build_metrics_block(agg2)

    fig.subplots_adjust(left=0.06, right=0.97, top=0.92, bottom=0.41, hspace=0.32, wspace=0.22)
    fig.text(0.05, 0.375, "Detailed Metrics", ha="left", va="bottom", fontsize=13, fontweight="bold")
    fig.text(
        0.05,
        0.358,
        "I/O, process activity, and shutdown summary for each executable",
        ha="left",
        va="bottom",
        fontsize=9,
        color="#5C5C5C",
    )
    fig.add_artist(Line2D([0.05, 0.95], [0.352, 0.352], transform=fig.transFigure, color="#D8D8D8", linewidth=1.0))

    card1_ax = fig.add_axes([0.05, 0.15, 0.42, 0.18])
    style_panel(card1_ax, exe1_color, "#F4FAFF")
    card1_ax.text(0.04, 0.93, agg1.label, ha="left", va="top", fontsize=11, fontweight="bold", color="#124A70")
    card1_ax.text(
        0.04,
        0.83,
        f"{context.exe1.filename} | Version {context.exe1.file_version} | Runs {context.runs_per_exe}",
        ha="left",
        va="top",
        fontsize=8.6,
        color="#35586C",
    )
    card1_ax.text(
        0.04,
        0.74,
        metrics_block_1,
        ha="left",
        va="top",
        fontsize=8.6,
        family="monospace",
        linespacing=1.3,
        color="#1F1F1F",
    )

    card2_ax = fig.add_axes([0.53, 0.15, 0.42, 0.18])
    style_panel(card2_ax, exe2_color, "#FFF7EC")
    card2_ax.text(0.04, 0.93, agg2.label, ha="left", va="top", fontsize=11, fontweight="bold", color="#8A4B00")
    card2_ax.text(
        0.04,
        0.83,
        f"{context.exe2.filename} | Version {context.exe2.file_version} | Runs {context.runs_per_exe}",
        ha="left",
        va="top",
        fontsize=8.6,
        color="#7A5A2A",
    )
    card2_ax.text(
        0.04,
        0.74,
        metrics_block_2,
        ha="left",
        va="top",
        fontsize=8.6,
        family="monospace",
        linespacing=1.3,
        color="#1F1F1F",
    )

    meta_ax = fig.add_axes([0.05, 0.045, 0.90, 0.075])
    style_panel(meta_ax, "#D3D6DA", "#FAFBFC")
    meta_ax.text(0.02, 0.86, "System & File Details", ha="left", va="top", fontsize=10, fontweight="bold", color="#2A2A2A")
    meta_ax.text(0.02, 0.58, footer_line_1, ha="left", va="top", fontsize=8.6, color="#3E3E3E")
    meta_ax.text(0.02, 0.34, exe_path_line_1, ha="left", va="top", fontsize=8.3, color="#4A4A4A")
    meta_ax.text(0.02, 0.10, exe_path_line_2, ha="left", va="bottom", fontsize=8.3, color="#4A4A4A")
    plt.savefig(output_png, dpi=160, bbox_inches="tight")
    plt.close(fig)


# ============================================================
# PRINTING
# ============================================================

def print_run_details(label: str, runs: List[RunMetrics]) -> None:
    print("=" * 70)
    print(f"{label} - PER RUN DETAILS")
    print("=" * 70)

    for i, r in enumerate(runs, start=1):
        print(f"[Run {i}]")
        print(f"  Launch time:            {r.launch_time_sec:.4f} sec")
        print(f"  Startup CPU avg:        {r.startup_avg_cpu_percent:.2f} %")
        print(f"  Startup memory avg:     {r.startup_avg_mem_mb:.2f} MB")
        print(f"  After-start CPU avg:    {r.steady_avg_cpu_percent:.2f} %")
        print(f"  After-start memory avg: {r.steady_avg_mem_mb:.2f} MB")
        print(f"  Peak memory:            {r.peak_mem_mb:.2f} MB")
        print(f"  Startup disk read:      {r.startup_read_bytes_mb:.2f} MB")
        print(f"  Startup disk write:     {r.startup_write_bytes_mb:.2f} MB")
        print(f"  Startup read ops:       {r.startup_read_count}")
        print(f"  Startup write ops:      {r.startup_write_count}")
        print(f"  Total disk read:        {r.total_read_bytes_mb:.2f} MB")
        print(f"  Total disk write:       {r.total_write_bytes_mb:.2f} MB")
        print(f"  Total read ops:         {r.total_read_count}")
        print(f"  Total write ops:        {r.total_write_count}")
        print(f"  Peak process count:     {r.peak_process_count}")
        print(f"  Peak child processes:   {r.peak_child_process_count}")
        print(f"  Unique processes seen:  {r.unique_process_count}")
        print(f"  Unique child processes: {r.unique_child_process_count}")
        print(f"  Shutdown time:          {r.shutdown_time_sec:.4f} sec")
        print(f"  Force-killed procs:     {r.force_killed_processes}")
        print(f"  Exited early:           {r.exited_early}")
        print(f"  Exit code:              {r.exit_code}")
        print("-" * 50)

    print()


def print_run_ranking(
    label1: str,
    runs1: List[RunMetrics],
    label2: str,
    runs2: List[RunMetrics]
) -> None:
    ranked = []

    for i, r in enumerate(runs1, start=1):
        ranked.append((r.launch_time_sec, label1, i, r))

    for i, r in enumerate(runs2, start=1):
        ranked.append((r.launch_time_sec, label2, i, r))

    ranked.sort(key=lambda x: x[0])

    print("=" * 70)
    print("RUN RANKING - FASTEST TO SLOWEST")
    print("=" * 70)

    for position, (launch_time, label, run_num, r) in enumerate(ranked, start=1):
        print(
            f"{position:>2}. {label} Run {run_num}  |  "
            f"{launch_time:.4f} sec  |  "
            f"Startup CPU {r.startup_avg_cpu_percent:.2f}%  |  "
            f"Startup Mem {r.startup_avg_mem_mb:.2f} MB  |  "
            f"Peak Mem {r.peak_mem_mb:.2f} MB"
        )

    print()


def print_summary(agg: AggregateMetrics) -> None:
    print("=" * 70)
    print(f"{agg.label} -> {agg.exe_path}")
    print("=" * 70)
    print(f"Runs:                        {agg.runs}")
    print(f"Avg launch time:            {agg.launch_time_sec_avg:.4f} sec")
    print(f"Min launch time:            {agg.launch_time_sec_min:.4f} sec")
    print(f"Max launch time:            {agg.launch_time_sec_max:.4f} sec")
    print(f"Avg startup CPU:            {agg.startup_avg_cpu_percent:.2f} %")
    print(f"Avg startup memory:         {agg.startup_avg_mem_mb:.2f} MB")
    print(f"Avg after-start CPU:        {agg.steady_avg_cpu_percent:.2f} %")
    print(f"Avg after-start memory:     {agg.steady_avg_mem_mb:.2f} MB")
    print(f"Avg peak memory:            {agg.peak_mem_mb:.2f} MB")
    print(f"Avg startup disk read:      {agg.startup_read_bytes_mb:.2f} MB")
    print(f"Avg startup disk write:     {agg.startup_write_bytes_mb:.2f} MB")
    print(f"Avg startup read ops:       {agg.startup_read_count:.0f}")
    print(f"Avg startup write ops:      {agg.startup_write_count:.0f}")
    print(f"Avg total disk read:        {agg.total_read_bytes_mb:.2f} MB")
    print(f"Avg total disk write:       {agg.total_write_bytes_mb:.2f} MB")
    print(f"Avg total read ops:         {agg.total_read_count:.0f}")
    print(f"Avg total write ops:        {agg.total_write_count:.0f}")
    print(f"Avg peak process count:     {agg.peak_process_count:.2f}")
    print(f"Avg peak child processes:   {agg.peak_child_process_count:.2f}")
    print(f"Avg unique processes seen:  {agg.unique_process_count:.2f}")
    print(f"Avg unique child processes: {agg.unique_child_process_count:.2f}")
    print(f"Avg shutdown time:          {agg.shutdown_time_sec_avg:.4f} sec")
    print(f"Avg force-killed procs:     {agg.force_killed_processes_avg:.2f}")
    print()


def print_winner(agg1: AggregateMetrics, agg2: AggregateMetrics) -> None:
    print("=" * 70)
    print("QUICK COMPARISON")
    print("=" * 70)

    faster = agg1 if agg1.launch_time_sec_avg < agg2.launch_time_sec_avg else agg2
    lighter_start = agg1 if agg1.startup_avg_mem_mb < agg2.startup_avg_mem_mb else agg2
    lighter_steady = agg1 if agg1.steady_avg_mem_mb < agg2.steady_avg_mem_mb else agg2
    lower_cpu_start = agg1 if agg1.startup_avg_cpu_percent < agg2.startup_avg_cpu_percent else agg2
    lower_cpu_steady = agg1 if agg1.steady_avg_cpu_percent < agg2.steady_avg_cpu_percent else agg2
    lower_startup_disk_read = agg1 if agg1.startup_read_bytes_mb < agg2.startup_read_bytes_mb else agg2
    fewer_helpers = agg1 if agg1.unique_child_process_count < agg2.unique_child_process_count else agg2
    faster_shutdown = agg1 if agg1.shutdown_time_sec_avg < agg2.shutdown_time_sec_avg else agg2

    print(f"Faster launch:              {faster.label}")
    print(f"Lower startup memory:       {lighter_start.label}")
    print(f"Lower after-start memory:   {lighter_steady.label}")
    print(f"Lower startup CPU:          {lower_cpu_start.label}")
    print(f"Lower after-start CPU:      {lower_cpu_steady.label}")
    print(f"Lower startup disk read:    {lower_startup_disk_read.label}")
    print(f"Fewer helper processes:     {fewer_helpers.label}")
    print(f"Faster shutdown:            {faster_shutdown.label}")
    print()


def print_benchmark_context(context: BenchmarkContext) -> None:
    print("=" * 70)
    print("BENCHMARK ENVIRONMENT")
    print("=" * 70)
    print(f"Run timestamp:               {context.run_timestamp}")
    print(f"CPU:                         {context.cpu_name}")
    print(f"RAM:                         {context.total_ram_gb:.1f} GB")
    print(f"Windows:                     {context.windows_version}")
    print(f"EXE 1:                       {context.exe1.label} ({context.exe1.filename})")
    print(f"EXE 1 path:                  {context.exe1.path}")
    print(f"EXE 1 version:               {context.exe1.file_version}")
    print(f"EXE 2:                       {context.exe2.label} ({context.exe2.filename})")
    print(f"EXE 2 path:                  {context.exe2.path}")
    print(f"EXE 2 version:               {context.exe2.file_version}")
    print(f"Runs per EXE:                {context.runs_per_exe}")
    print()


# ============================================================
# MAIN
# ============================================================

def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Benchmark two executables and compare CPU, memory, disk I/O, "
            "process activity, launch time, and shutdown time."
        )
    )
    parser.add_argument("--exe1", required=True, help="Path to first EXE")
    parser.add_argument("--exe2", required=True, help="Path to second EXE")
    parser.add_argument("--label1", default="EXE 1", help="Display label for first EXE")
    parser.add_argument("--label2", default="EXE 2", help="Display label for second EXE")
    parser.add_argument("--args1", nargs="*", default=[], help="Arguments for first EXE")
    parser.add_argument("--args2", nargs="*", default=[], help="Arguments for second EXE")
    parser.add_argument("--runs", type=int, default=3, help="Number of runs per EXE")
    parser.add_argument("--startup-window", type=float, default=5.0, help="Seconds counted as startup")
    parser.add_argument("--steady-window", type=float, default=5.0, help="Seconds counted as after-start")
    parser.add_argument("--sample-interval", type=float, default=0.2, help="Sampling interval in seconds")
    parser.add_argument("--no-auto-terminate", action="store_true", help="Do not auto-close the EXE after sampling")
    parser.add_argument("--output", default="exe_benchmark.png", help="Output PNG graph file")
    parser.add_argument(
        "--priority",
        default="normal",
        choices=["idle", "below-normal", "normal", "above-normal", "high", "realtime"],
        help="Windows process priority for launched EXEs"
    )
    args = parser.parse_args()

    auto_terminate = not args.no_auto_terminate
    context = build_benchmark_context(args.exe1, args.exe2, args.label1, args.label2, args.runs)

    all_runs_1: List[RunMetrics] = []
    all_runs_2: List[RunMetrics] = []

    print(f"Benchmarking {args.label1}...")
    for i in range(args.runs):
        print(f"  Run {i + 1}/{args.runs}")
        result = benchmark_exe_once(
            exe_path=args.exe1,
            args=args.args1,
            startup_window=args.startup_window,
            steady_window=args.steady_window,
            sample_interval=args.sample_interval,
            auto_terminate=auto_terminate,
            priority=args.priority
        )
        all_runs_1.append(result)

    print()
    print(f"Benchmarking {args.label2}...")
    for i in range(args.runs):
        print(f"  Run {i + 1}/{args.runs}")
        result = benchmark_exe_once(
            exe_path=args.exe2,
            args=args.args2,
            startup_window=args.startup_window,
            steady_window=args.steady_window,
            sample_interval=args.sample_interval,
            auto_terminate=auto_terminate,
            priority=args.priority
        )
        all_runs_2.append(result)

    print()
    print_run_details(args.label1, all_runs_1)
    print_run_details(args.label2, all_runs_2)
    print_run_ranking(args.label1, all_runs_1, args.label2, all_runs_2)

    agg1 = aggregate_runs(args.label1, args.exe1, all_runs_1)
    agg2 = aggregate_runs(args.label2, args.exe2, all_runs_2)

    print()
    print_summary(agg1)
    print_summary(agg2)
    print_winner(agg1, agg2)
    print_benchmark_context(context)

    plot_comparison(agg1, agg2, all_runs_1, all_runs_2, context, args.output)
    print(f"Graph saved to: {args.output}")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nCancelled by user.")
        raise SystemExit(1)