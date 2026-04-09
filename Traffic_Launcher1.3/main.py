#!/usr/bin/env python3

import os
import shutil
import subprocess
import sys
import shlex
import time
import threading
import re
import datetime

# Global reconnection lock - ensures only one monitor handles NOT ASSOCIATED
RECONNECTION_IN_PROGRESS = threading.Lock()
RECONNECTION_TRIGGERED = threading.Event()
# Track modes that have been marked failed to avoid duplicate work across monitors
FAILED_MODES = set()
FAILED_MODES_LOCK = threading.Lock()
# Graceful fatal-stop controls (safe replacement for os._exit)
FATAL_STOP_EVENT = threading.Event()
FATAL_STOP_REASON = None
FATAL_STOP_LOCK = threading.Lock()
# Flag to rerun current test after successful reconnection
RERUN_CURRENT_MODE = threading.Event()
RERUN_MODE_NAME = None
RERUN_LOCK = threading.Lock()
# Store connection script name from CLI argument (e.g., sl_connect.sh, 2G_connect.sh, etc.)
CONNECTION_SCRIPT = "sl_connect.sh"  # Default value, will be set from sys.argv[1] in main()
# The .sh file that launched this Python process (detected from parent process at startup)
CALLER_SCRIPT = None
# Global log file handle for monitor logs
LOG_FILE = None

# ------------------ CONFIG ------------------
# Edit these values to match your DUT / test parameters
CONFIG = {
    "DUTS_IP": "172.16.10.25",          # DUT IP address to SSH into (management/control plane)
    "DUTS_USER": "root",              # SSH user for DUT
    "DUTS_PASSWORD": "hrun*10",     # Password for SSH (used with sshpass)
    "STATIC_TARGET": "192.168.50.25",   # DUT's data plane IP for iperf traffic (used when DUT is server)
    "LOCAL_IP": "192.168.50.30",     # Local machine's data plane IP for iperf traffic (used when local is server)
    "WINDOW": "60K",                  # TCP window size (e.g. 30k)
    "TIME": "1800",                     # test duration in seconds
    "UDP_RATE": "35M",                # UDP data rate for iperf (e.g. 35M)
    "IPERF_BIN": "iperf",             # iperf executable
    "OUTPUT_NAME": "TAG73_CPUSS_1255_ML_2G_UDP_RX",
    "ENABLE_WL_COUNTERS": True,       # Set to True to enable wl counters calls, False to disable
    # MODE: one of 'tcp_rx','tcp_tx','udp_rx','udp_tx','all'
    # - 'tcp_rx': DUT is server (receives) -> remote:server, local:client
    # - 'tcp_tx': DUT is client (sends) -> local:server, remote:client
    # - 'udp_rx': DUT is server (receives UDP)
    # - 'udp_tx': DUT is client (sends UDP)
    # - 'all': runs all tests (tcp_rx, tcp_tx, udp_rx, udp_tx)
    # 
    # MONITORING: Real-time monitoring checks for 0 Mbps throughput for 10 seconds.
    # When detected, runs 'wl ver' on DUT. If FWID found, checks 'wl status'.
    # If 'wl status' shows 'NOT ASSOCIATED', runs reconnection and restarts script.
    #"MODE": "tcp_tx, tcp_rx, udp_tx, udp_rx",
    "MODE": "udp_rx",
    "PRE_TEST_SLEEP": "20",         # seconds to wait after pre-test cleanup before starting each mode
}


def _detect_caller_script(here):
    """Return the absolute path of the .sh script that launched this process (via parent PID).
    Works on Linux by reading /proc/<ppid>/cmdline. Returns None if not detectable."""
    try:
        ppid = os.getppid()
        cmdline_path = f"/proc/{ppid}/cmdline"
        if os.path.exists(cmdline_path):
            with open(cmdline_path, 'rb') as f:
                parts = f.read().decode('utf-8', errors='replace').split('\x00')
            for part in parts:
                if part.endswith('.sh'):
                    # Try absolute path first, then relative to script directory
                    if os.path.isabs(part) and os.path.exists(part):
                        return part
                    local = os.path.join(here, os.path.basename(part))
                    if os.path.exists(local):
                        return local
    except Exception:
        pass
    return None


def find_terminal():
    candidates = [
        ("gnome-terminal", ["--"]),
        ("xfce4-terminal", ["--command"]),
        ("konsole", ["-e"]),
        ("xterm", ["-e"]),
        ("lxterminal", ["-e"]),
    ]
    for name, arg in candidates:
        if shutil.which(name):
            return name, arg
    return None, None


def check_prereqs():
    missing = []
    term, _ = find_terminal()
    if not term:
        missing.append("terminal emulator (gnome-terminal, xterm, konsole, etc.)")
    if not shutil.which("ssh"):
        missing.append("ssh")
    if not shutil.which(CONFIG["IPERF_BIN"]):
        missing.append(CONFIG["IPERF_BIN"])
    # sshpass is optional but recommended for non-interactive password
    if not shutil.which("sshpass"):
        log_print("Warning: 'sshpass' not found. You will need to enter the DUT password interactively when prompted.")
    if missing:
        log_print("Missing required tools: " + ", ".join(missing))
        sys.exit(1)


def open_terminal_with_command(term, term_arg, command, title=None):
    # Build the terminal invocation depending on emulator.
    # Add message at end and wait 5 seconds before closing terminal
    end_msg = "; echo ''; echo '=== Test completed - Terminal will close in 5 seconds ==='; sleep 5"
    
    if term == "gnome-terminal":
        cmd = [term]
        if title:
            cmd += ["--title", title]
        cmd += ["--", "bash", "-lc", command + end_msg]
    elif term == "xfce4-terminal":
        cmd = [term]
        if title:
            cmd += ["--title", title]
        cmd += ["--command", f"bash -lc \"{command}{end_msg}\""]
    elif term == "konsole":
        cmd = [term, "-e", "bash", "-lc", command + end_msg]
    elif term == "xterm" or term == "lxterminal":
        cmd = [term, "-e", "bash", "-lc", command + end_msg]
    else:
        # generic fallback - ensure bash stays open
        full_cmd = f"bash -lc \"{command}{end_msg}\""
        cmd = [term] + term_arg + [full_cmd]

    # Ensure we spawn detached so our launcher continues
    log_print("Launching terminal: " + " ".join(cmd))
    subprocess.Popen(cmd)


def build_server_client_commands(mode=None):
    """Return (server_cmd, client_cmd, server_on_remote:bool) based on MODE or provided mode."""
    if mode is None:
        mode = CONFIG.get("MODE", "tcp_rx")
    iperf = CONFIG.get("IPERF_BIN", "iperf")
    window = CONFIG.get("WINDOW")
    t = CONFIG.get("TIME")
    udp_rate = CONFIG.get("UDP_RATE")
    dut_ssh = CONFIG.get("DUTS_IP")  # IP for SSH (management plane)
    static_target = CONFIG.get("STATIC_TARGET")  # DUT's data plane IP for iperf traffic
    local_ip_config = CONFIG.get("LOCAL_IP")  # Local machine's data plane IP

    # Detect iperf version to use correct flags
    is_iperf3 = "iperf3" in os.path.basename(iperf)

    # Server base
    if mode.startswith("tcp"):
        if is_iperf3:
            # iperf3: window is client-only; server needs no extra flags
            server_flags = f"-s -i 1"
            client_flags = f"-i 1 -t {t} -w {window}"
        else:
            server_flags = f"-s -i 1 -w {window}"
            client_flags = f"-i 1 -t {t} -w {window}"
        use_udp = False
    else:
        if is_iperf3:
            # iperf3: server does not take -u (accepts both TCP/UDP without it)
            server_flags = f"-s -i 1"
            client_flags = f"-i 1 -t {t} -u -b {udp_rate}"
        else:
            server_flags = f"-s -i 1 -u"
            client_flags = f"-i 1 -t {t} -u -b {udp_rate}"
        use_udp = True

    if mode.endswith("_rx"):
        # DUT receives -> server runs on DUT (remote), local is client
        server_on_remote = True
        server_cmd = f"{iperf} {server_flags}"
        # Client targets STATIC_TARGET (DUT's data plane IP)
        target = static_target or dut_ssh
        client_cmd = f"{iperf} -c {target} {client_flags}"
    else:
        # DUT sends -> server runs locally, client runs on DUT (remote)
        server_on_remote = False
        # Use configured LOCAL_IP or auto-detect
        if local_ip_config:
            local_ip = local_ip_config
        else:
            local_ip = detect_local_ip(dut_ssh)
            log_print(f"Warning: LOCAL_IP not configured, auto-detected: {local_ip}")
        server_cmd = f"{iperf} {server_flags}"
        client_cmd = f"{iperf} -c {local_ip} {client_flags}"

    return server_cmd, client_cmd, server_on_remote


def detect_local_ip(remote_ip):
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((remote_ip, 9))
        local_ip = s.getsockname()[0]
    except Exception:
        local_ip = "127.0.0.1"
    finally:
        s.close()
    return local_ip


def build_ssh_base(dut_ip, user, password):
    if shutil.which("sshpass") and password:
        return f"sshpass -p {shlex.quote(password)} ssh -o StrictHostKeyChecking=no {user}@{dut_ip}"
    return f"ssh -o StrictHostKeyChecking=no {user}@{dut_ip}"


def log_print(message="", end="\n"):
    """Print to console and write to monitor log file."""
    global LOG_FILE
    print(message, end=end)
    if LOG_FILE:
        try:
            LOG_FILE.write(str(message) + end)
            LOG_FILE.flush()
        except Exception:
            pass


def pre_test_cleanup(sleep_seconds=20, dut_ip=None, user=None, password=None):
    """Run cleanup before each test mode starts from the main launcher terminal.

    Executes local iperf cleanup and remote DUT iperf cleanup (forceful),
    then waits before the next mode starts.
    """
    log_print("\n" + "=" * 60)
    log_print("[PRE-TEST] Running cleanup before starting next test")
    log_print("[PRE-TEST] Command intent: pkill -9 iperf (local + remote DUT)")
    log_print("=" * 60)

    # Kill local iperf processes (forceful)
    subprocess.run("pkill -9 iperf 2>/dev/null || true", shell=True)
    subprocess.run("killall -9 iperf 2>/dev/null || true", shell=True)
    log_print("[PRE-TEST] Local cleanup done: pkill -9 iperf; killall -9 iperf")

    # Kill remote DUT iperf processes (forceful with verification)
    if dut_ip and user:
        try:
            ssh_base = build_ssh_base(dut_ip, user, password)
            log_print(f"[PRE-TEST] Killing iperf on DUT: {dut_ip}")
            
            # Try multiple kill methods for robustness
            kill_commands = "pkill -9 iperf 2>/dev/null || true; killall -9 iperf 2>/dev/null || true"
            result = subprocess.run(
                f"{ssh_base} '{kill_commands}'",
                shell=True,
                capture_output=True,
                text=True,
                timeout=10
            )
            log_print("[PRE-TEST] Remote DUT cleanup done: pkill -9 iperf; killall -9 iperf")
            
            # Wait a moment for processes to actually terminate
            time.sleep(2)
            
            # Verify no iperf processes remain on DUT
            verify_result = subprocess.run(
                f"{ssh_base} 'pgrep iperf 2>/dev/null || echo NONE'",
                shell=True,
                capture_output=True,
                text=True,
                timeout=5
            )
            if verify_result.stdout.strip() != "NONE" and verify_result.stdout.strip():
                log_print(f"[PRE-TEST] WARNING: iperf processes still running on DUT: {verify_result.stdout.strip()}")
                # Try one more time with explicit PIDs
                pids = verify_result.stdout.strip().split('\n')
                for pid in pids:
                    if pid.strip():
                        subprocess.run(f"{ssh_base} 'kill -9 {pid.strip()} 2>/dev/null || true'", shell=True, timeout=5)
                log_print("[PRE-TEST] Attempted to kill remaining PIDs")
            else:
                log_print("[PRE-TEST] Verified: No iperf processes on DUT")
                
        except subprocess.TimeoutExpired:
            log_print("[PRE-TEST] WARNING: Remote cleanup timed out")
        except Exception as e:
            log_print(f"[PRE-TEST] WARNING: Remote cleanup error: {e}")

    if sleep_seconds > 0:
        log_print(f"[PRE-TEST] Sleeping {sleep_seconds} seconds before starting test")
        time.sleep(sleep_seconds)


def request_fatal_stop(reason, dut_ip, user, password, stop_event=None):
    """Request a process-wide graceful stop, kill iperf safely, and record first failure reason."""
    global FATAL_STOP_REASON

    with FATAL_STOP_LOCK:
        first_request = not FATAL_STOP_EVENT.is_set()
        if first_request:
            FATAL_STOP_REASON = reason
            log_print("\n" + "=" * 60)
            log_print(f"[FATAL] {reason}")
            log_print("[FATAL] Graceful shutdown requested")
            log_print("=" * 60)
        FATAL_STOP_EVENT.set()

    if stop_event is not None:
        stop_event.set()

    # Forceful kill of iperf processes
    subprocess.run("pkill -9 iperf 2>/dev/null || true", shell=True)
    subprocess.run("killall -9 iperf 2>/dev/null || true", shell=True)
    try:
        ssh_base = build_ssh_base(dut_ip, user, password)
        subprocess.run(f"{ssh_base} 'pkill -9 iperf 2>/dev/null || true; killall -9 iperf 2>/dev/null || true'", shell=True, timeout=10)
    except Exception:
        pass


def handle_not_associated_reconnect_and_restart(dut_ip, user, password, term=None, term_arg=None, max_retries=2, filepath=None, mode_name=""):
    """
    Handles NOT ASSOCIATED situation by:
    1. Killing iperf processes
    2. Running connection script on DUT to reconnect (reads command from wrap_5g_2g.sh)
    3. Checking wl status after reconnection
    4. Returns True if reconnection successful, False otherwise
    
    Does NOT restart script or exit - caller decides what to do.
    Uses the CONNECTION_SCRIPT global variable to find the correct plink command.
    """
    global CONNECTION_SCRIPT
    
    log_print("\n" + "="*60)
    log_print("[RECONNECT] DUT is NOT ASSOCIATED - Attempting reconnection")
    log_print(f"[RECONNECT] Using connection script: {CONNECTION_SCRIPT}")
    log_print("="*60)
    
    # Read plink command from the caller .sh script (dynamic, not hardcoded)
    here = os.path.dirname(os.path.abspath(__file__))
    reconnect_cmd = None
    plink_base = None

    # Extract script name without path for searching
    script_name = os.path.basename(CONNECTION_SCRIPT)

    # Use the detected caller script first; fall back to searching all .sh files
    import glob
    candidate_files = ([CALLER_SCRIPT] if CALLER_SCRIPT else []) + [
        f for f in glob.glob(os.path.join(here, "*.sh"))
        if f != CALLER_SCRIPT
    ]

    try:
        for sh_file in candidate_files:
            if not sh_file or not os.path.exists(sh_file):
                continue
            try:
                with open(sh_file, 'r') as f:
                    for line in f:
                        if 'plink' in line and script_name in line and not line.strip().startswith('#'):
                            reconnect_cmd = line.strip()
                            if 'plink -ssh -pw' in line:
                                parts = line.split()
                                pw_idx = parts.index('-pw')
                                password_in_file = parts[pw_idx + 1]
                                user_host = parts[pw_idx + 2]
                                plink_base = f"plink -ssh -pw {password_in_file} {user_host}"
                            break
            except Exception:
                continue
            if reconnect_cmd:
                log_print(f"[RECONNECT] Found command in: {os.path.basename(sh_file)}")
                break

        if not reconnect_cmd:
            log_print(f"[RECONNECT] WARNING: Could not find plink {script_name} command in any .sh file")
            log_print("[RECONNECT] Using fallback command")
            plink_base = f"plink -ssh -pw {password} {user}@{dut_ip}"
            reconnect_cmd = f"{plink_base} sudo sh -x {script_name}"
        else:
            log_print(f"[RECONNECT] Using plink command for {script_name}:")
            # Mask password in display
            display_cmd = reconnect_cmd
            if '-pw' in display_cmd:
                parts = display_cmd.split()
                pw_idx = parts.index('-pw')
                parts[pw_idx + 1] = '******'
                display_cmd = ' '.join(parts)
            log_print(f"[RECONNECT] {display_cmd}")
    except Exception as e:
        log_print(f"[RECONNECT] Error searching .sh files: {e}")
        log_print("[RECONNECT] Using fallback command")
        plink_base = f"plink -ssh -pw {password} {user}@{dut_ip}"
        reconnect_cmd = f"{plink_base} sudo sh -x {script_name}"
    
    # Kill all iperf processes (local and remote) - forceful
    log_print("[RECONNECT] Killing all iperf processes...")
    subprocess.run("pkill -9 iperf 2>/dev/null || true", shell=True)
    subprocess.run("killall -9 iperf 2>/dev/null || true", shell=True)
    try:
        if plink_base:
            subprocess.run(f"{plink_base} 'pkill -9 iperf 2>/dev/null || true; killall -9 iperf 2>/dev/null || true'", shell=True, timeout=10)
    except:
        pass
    
    # Attempt reconnection with retries
    for attempt in range(1, max_retries + 1):
        log_print(f"\n[RECONNECT] Attempt {attempt}/{max_retries}: Running {script_name} on DUT...")
        
        try:
            # Run the exact command from wrap_5g_2g.sh
            reconnect_result = subprocess.run(
                reconnect_cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=60
            )
            if reconnect_result.stdout:
                log_print(f"[RECONNECT] {script_name} output: {reconnect_result.stdout[:300]}")
        except subprocess.TimeoutExpired:
            log_print(f"[RECONNECT] {script_name} timed out")
        except Exception as e:
            log_print(f"[RECONNECT] Error running {script_name}: {e}")
        
        # Wait for connection to stabilize
        log_print(f"[RECONNECT] Waiting 10 seconds for connection to stabilize...")
        time.sleep(10)
        
        # Check wl status after reconnection
        log_print(f"[RECONNECT] Checking wl status after reconnection attempt {attempt}...")
        try:
            status_cmd = f"{plink_base} 'wl status'"
            # Mask password for display
            display_status = status_cmd.replace(password, '******') if password in status_cmd else status_cmd
            log_print(f"[RECONNECT] Running: {display_status}")
            status_result = subprocess.run(
                status_cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=10
            )
            wl_status_output = status_result.stdout + status_result.stderr
            log_print(f"[RECONNECT] wl status output: {wl_status_output[:300]}")
            
            # Run wl counters and save to logs folder (if enabled)
            if filepath and CONFIG.get("ENABLE_WL_COUNTERS", False):
                wl_counters_cmd = "wl counters"
                log_print(f"[RECONNECT] Running 'wl counters' - saving to logs folder")
                try:
                    counters_result = subprocess.run(
                        f"{plink_base} '{wl_counters_cmd}'",
                        shell=True,
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    wl_counters_output = counters_result.stdout + counters_result.stderr
                    
                    # Save wl counters to the logs subfolder
                    main_dir = os.path.dirname(filepath)
                    logs_subfolder = os.path.join(main_dir, "logs")
                    os.makedirs(logs_subfolder, exist_ok=True)
                    
                    # Save wl counters output with timestamp
                    timestamp = time.strftime("%Y%m%d_%H%M%S")
                    reconnect_suffix = f"reconnect_attempt{attempt}"
                    counters_file = os.path.join(logs_subfolder, f"wl_counters_{mode_name}_{reconnect_suffix}_{timestamp}.txt")
                    with open(counters_file, 'w') as cf:
                        cf.write(f"=== WL COUNTERS OUTPUT (RECONNECTION) ===\n")
                        cf.write(f"Mode: {mode_name}\n")
                        cf.write(f"Reconnection Attempt: {attempt}\n")
                        cf.write(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                        cf.write(f"{'='*50}\n\n")
                        cf.write(wl_counters_output)
                    
                    log_print(f"[RECONNECT] wl counters saved to: {counters_file}")
                except Exception as e:
                    log_print(f"[RECONNECT] Error running or saving wl counters: {e}")
            
            if "NOT ASSOCIATED" not in wl_status_output.upper():
                # SUCCESS - DUT is now associated
                log_print("\n" + "="*60)
                log_print(f"[RECONNECT] SUCCESS! DUT is now ASSOCIATED after attempt {attempt}")
                log_print("="*60 + "\n")
                return True
            else:
                log_print(f"[RECONNECT] Attempt {attempt} FAILED - DUT still NOT ASSOCIATED")
                
        except Exception as e:
            log_print(f"[RECONNECT] Error checking wl status: {e}")
    
    # All attempts failed
    log_print("\n" + "="*60)
    log_print(f"[RECONNECT] FAILED - DUT still NOT ASSOCIATED after {max_retries} attempts")
    log_print("[RECONNECT] Skipping this test and moving to next")
    log_print("="*60 + "\n")
    return False



def mark_mode_as_failed(filepath, mode_name, reason="UNKNOWN"):
    """Mark the current test mode as failed: preserve server/client outputs and write a marker in logs.

    - Renames existing server_<mode>.txt and client_<mode>.txt to include _FAILED_<timestamp>
    - Writes a marker file in the run's logs folder with reason and preserved filenames
    This function is idempotent for a given base mode per process run.
    """
    try:
        base_mode = mode_name.rsplit('_', 1)[0]
    except Exception:
        base_mode = mode_name

    with FAILED_MODES_LOCK:
        if base_mode in FAILED_MODES:
            log_print(f"[MARK] Mode already marked failed: {base_mode}")
            return
        FAILED_MODES.add(base_mode)

    main_dir = os.path.dirname(filepath)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    server_file = os.path.join(main_dir, f"server_{base_mode}.txt")
    client_file = os.path.join(main_dir, f"client_{base_mode}.txt")

    preserved = []
    for src in (server_file, client_file):
        if os.path.exists(src):
            base, ext = os.path.splitext(src)
            dst = f"{base}_FAILED_{timestamp}{ext}"
            try:
                os.rename(src, dst)
                preserved.append(os.path.basename(dst))
                log_print(f"[MARK] Preserved {src} -> {dst}")
            except Exception:
                try:
                    shutil.copy2(src, dst)
                    preserved.append(os.path.basename(dst))
                    log_print(f"[MARK] Copied {src} -> {dst}")
                except Exception as e:
                    log_print(f"[MARK] Failed to preserve {src}: {e}")
        else:
            log_print(f"[MARK] File not found, skipping: {src}")

    # Ensure logs folder exists and write a marker
    logs_dir = os.path.join(main_dir, "logs")
    os.makedirs(logs_dir, exist_ok=True)
    marker_file = os.path.join(logs_dir, f"FAILED_{base_mode}_{timestamp}.txt")
    try:
        with open(marker_file, 'w') as mf:
            mf.write(f"Mode: {base_mode}\n")
            mf.write(f"Reason: {reason}\n")
            mf.write(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            mf.write("Preserved files:\n")
            for p in preserved:
                mf.write(f" - {p}\n")
        log_print(f"[MARK] Failure marker written: {marker_file}")
    except Exception as e:
        log_print(f"[MARK] Error writing marker file: {e}")


def monitor_file_for_zero_throughput(filepath, dut_ip, user, password, stop_event, mode_name, ping_lock=None, term=None, term_arg=None):
    """
    Monitors output file in real-time for traffic and throughput issues.
    
    STARTUP CHECK (first 20 seconds):
    - Waits for non-zero traffic to start within 20 seconds
    - If no traffic detected after 20s, runs diagnostics (wl ver, wl status)
    - Stops test if FWID not found or DUT is NOT ASSOCIATED
    - Does NOT count these diagnostic runs in statistics
    
    NORMAL MONITORING (ongoing):
    If zero throughput detected for 10 seconds:
    1. Runs 'wl ver' on DUT to check for FWID
    2. If FWID found, runs 'wl status' to check association
    3. If 'NOT ASSOCIATED' found, stops the test
    4. If associated, runs ping test to STATIC_TARGET (only one ping at a time)
    5. If ping fails, stops the test
    6. Otherwise continues waiting
    """
    global RECONNECTION_TRIGGERED
    
    zero_count = 0
    timeout_count = 0
    consecutive_zeros = 0
    zero_start_time = None
    wl_ver_count = 0
    wl_status_count = 0
    
    log_print(f"[Monitor] Starting monitor for {filepath} ({mode_name})")

    if FATAL_STOP_EVENT.is_set():
        log_print(f"[Monitor] Fatal stop already active - exiting monitor ({mode_name})")
        return
    
    # Wait for file to be created
    wait_time = 0
    while not os.path.exists(filepath) and wait_time < 10:
        # Check if reconnection has been triggered by another monitor
        if RECONNECTION_TRIGGERED.is_set():
            log_print(f"[Monitor] Reconnection triggered by another monitor - exiting ({mode_name})")
            return
        time.sleep(0.5)
        wait_time += 0.5
    
    if not os.path.exists(filepath):
        log_print(f"[Monitor] File {filepath} not created, exiting monitor")
        return
    
    try:
        with open(filepath, 'r') as f:
            # Move to end of file
            f.seek(0, 2)
            
            # STARTUP CHECK: Verify traffic starts within 20 seconds
            log_print(f"[Monitor] Startup check - waiting 20s for traffic to begin ({mode_name})")
            startup_start_time = time.time()
            startup_traffic_detected = False
            
            while not stop_event.is_set():
                # Check if reconnection has been triggered by another monitor
                if RECONNECTION_TRIGGERED.is_set():
                    log_print(f"[Monitor] Reconnection triggered by another monitor - exiting ({mode_name})")
                    return
                
                startup_elapsed = time.time() - startup_start_time
                
                # Break out of startup check after 20 seconds
                if startup_elapsed >= 20:
                    break
                
                line = f.readline()
                if not line:
                    time.sleep(0.1)
                    continue
                
                # Check for any non-zero throughput (indicates traffic started)
                # Look for patterns like "59.0 Mbits/sec" but NOT "0.0 Mbits/sec"
                if re.search(r'\s+[1-9]\d*(?:\.\d+)?\s+[KMG]?bits/sec', line, re.IGNORECASE):
                    startup_traffic_detected = True
                    log_print(f"[Monitor] Startup check PASSED - traffic detected at {startup_elapsed:.1f}s ({mode_name})")
                    break
            
            # If no traffic detected in 20 seconds, EXIT THE ENTIRE SCRIPT
            if not startup_traffic_detected and not stop_event.is_set():
                log_print(f"[Monitor] STARTUP CHECK FAILED - No traffic detected after 20 seconds ({mode_name})")
                request_fatal_stop(f"STARTUP_CHECK_FAILED:{mode_name}", dut_ip, user, password, stop_event=stop_event)
                return
            
            # NORMAL MONITORING: Continue with regular zero throughput monitoring
            log_print(f"[Monitor] Starting normal monitoring phase ({mode_name})")
            
            while not stop_event.is_set():
                if FATAL_STOP_EVENT.is_set():
                    log_print(f"[Monitor] Fatal stop active - exiting ({mode_name})")
                    return

                # Check if reconnection has been triggered by another monitor
                if RECONNECTION_TRIGGERED.is_set():
                    log_print(f"[Monitor] Reconnection triggered by another monitor - exiting ({mode_name})")
                    return
                
                line = f.readline()
                if not line:
                    time.sleep(0.1)
                    continue
                
                # Check for zero throughput patterns
                # iperf output: "0.0 Mbits/sec" or "0 Mbits/sec" but NOT "59.0 Mbits/sec"
                # Look for whitespace + zeros + optional(.zeros) + whitespace + unit
                if re.search(r'\s+0+(?:\.0+)?\s+[KMG]?bits/sec', line, re.IGNORECASE):
                    zero_count += 1
                    consecutive_zeros += 1
                    
                    if zero_start_time is None:
                        zero_start_time = time.time()
                    
                    elapsed = time.time() - zero_start_time
                    log_print(f"[Monitor] Zero throughput detected (count: {zero_count}, consecutive: {consecutive_zeros}, elapsed: {elapsed:.1f}s) in {mode_name}")
                    log_print(f"[Monitor] Line: {line.strip()}")
                    
                    # Check if 1 second of zero throughput have elapsed (normal monitoring)
                    if elapsed >= 1:
                        log_print(f"[Monitor] 1 zero stall detected - running diagnostics")
                        
                        # First run wl counters immediately when 1 zero stall detected (if enabled)
                        ssh_base = build_ssh_base(dut_ip, user, password)
                        if CONFIG.get("ENABLE_WL_COUNTERS", False):
                            wl_counters_cmd = "wl counters"
                            log_print(f"[Monitor] Running 'wl counters' immediately after 1 zero stall detected")
                            try:
                                counters_result = subprocess.run(
                                    f"{ssh_base} '{wl_counters_cmd}'",
                                    shell=True,
                                    capture_output=True,
                                    text=True,
                                    timeout=5
                                )
                                wl_counters_output = counters_result.stdout + counters_result.stderr
                                
                                # Save wl counters to the logs subfolder
                                main_dir = os.path.dirname(filepath)
                                logs_subfolder = os.path.join(main_dir, "logs")
                                os.makedirs(logs_subfolder, exist_ok=True)
                                
                                # Save wl counters output with timestamp
                                timestamp = time.strftime("%Y%m%d_%H%M%S")
                                counters_file = os.path.join(logs_subfolder, f"wl_counters_{mode_name}_1zerostall_{timestamp}.txt")
                                with open(counters_file, 'w') as cf:
                                    cf.write(f"=== WL COUNTERS OUTPUT (1 ZERO STALL DETECTED) ===\n")
                                    cf.write(f"Mode: {mode_name}\n")
                                    cf.write(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                                    cf.write(f"{'='*50}\n\n")
                                    cf.write(wl_counters_output)
                                
                                log_print(f"[Monitor] wl counters (1 zero stall) saved to: {counters_file}")
                            except Exception as e:
                                log_print(f"[Monitor] Error running or saving wl counters (1 zero stall): {e}")
                        
                        # Run wl ver command on DUT via SSH
                        wl_ver_cmd = "wl ver"
                        
                        try:
                            # Check wl ver for FWID
                            wl_ver_count += 1
                            log_print(f"[Monitor] Running 'wl ver' (count: {wl_ver_count})")
                            result = subprocess.run(
                                f"{ssh_base} '{wl_ver_cmd}'",
                                shell=True,
                                capture_output=True,
                                text=True,
                                timeout=5
                            )
                            wl_ver_output = result.stdout + result.stderr
                            log_print(f"[Monitor] wl ver output: {wl_ver_output[:200]}")
                            
                            # Check if FWID is in the output
                            if "FWID" in wl_ver_output or "fwid" in wl_ver_output.lower():
                                log_print(f"[Monitor] FWID found in wl ver output - checking wl status")
                                
                                # Run wl status command
                                wl_status_cmd = "wl status"
                                wl_status_count += 1
                                log_print(f"[Monitor] Running 'wl status' (count: {wl_status_count})")
                                status_result = subprocess.run(
                                    f"{ssh_base} '{wl_status_cmd}'",
                                    shell=True,
                                    capture_output=True,
                                    text=True,
                                    timeout=5
                                )
                                wl_status_output = status_result.stdout + status_result.stderr
                                log_print(f"[Monitor] wl status output: {wl_status_output[:300]}")
                                
                                # Run wl counters and save to run folder (if enabled)
                                if CONFIG.get("ENABLE_WL_COUNTERS", False):
                                    wl_counters_cmd = "wl counters"
                                    log_print(f"[Monitor] Running 'wl counters' - saving to run folder")
                                    try:
                                        counters_result = subprocess.run(
                                            f"{ssh_base} '{wl_counters_cmd}'",
                                            shell=True,
                                            capture_output=True,
                                            text=True,
                                            timeout=5
                                        )
                                        wl_counters_output = counters_result.stdout + counters_result.stderr
                                        
                                        # Save wl counters to the logs subfolder
                                        main_dir = os.path.dirname(filepath)
                                        logs_subfolder = os.path.join(main_dir, "logs")
                                        os.makedirs(logs_subfolder, exist_ok=True)
                                        
                                        # Save wl counters output with timestamp
                                        timestamp = time.strftime("%Y%m%d_%H%M%S")
                                        counters_file = os.path.join(logs_subfolder, f"wl_counters_{mode_name}_{timestamp}.txt")
                                        with open(counters_file, 'w') as cf:
                                            cf.write(f"=== WL COUNTERS OUTPUT ===\n")
                                            cf.write(f"Mode: {mode_name}\n")
                                            cf.write(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                                            cf.write(f"{'='*50}\n\n")
                                            cf.write(wl_counters_output)
                                        
                                        log_print(f"[Monitor] wl counters saved to: {counters_file}")
                                    except Exception as e:
                                        log_print(f"[Monitor] Error running or saving wl counters: {e}")
                                
                                # Check if NOT ASSOCIATED
                                if "NOT ASSOCIATED" in wl_status_output.upper():
                                    log_print(f"[Monitor] DUT is NOT ASSOCIATED during normal monitoring")
                                    # Mark mode as failed
                                    try:
                                        mark_mode_as_failed(filepath, mode_name, reason="NOT_ASSOCIATED")
                                    except Exception as e:
                                        log_print(f"[MARK] Error marking mode as failed: {e}")
                                    
                                    # Stop iperf - forceful kill
                                    stop_event.set()
                                    subprocess.run("pkill -9 iperf 2>/dev/null || true", shell=True)
                                    subprocess.run("killall -9 iperf 2>/dev/null || true", shell=True)
                                    subprocess.run(f"{ssh_base} 'pkill -9 iperf 2>/dev/null || true; killall -9 iperf 2>/dev/null || true'", shell=True)

                                    reconnect_success = None
                                    attempted_reconnect = False

                                    # Ensure only one monitor attempts reconnection
                                    if RECONNECTION_IN_PROGRESS.acquire(blocking=False):
                                        attempted_reconnect = True
                                        RECONNECTION_TRIGGERED.set()
                                        try:
                                            # Attempt reconnection (2 tries)
                                            reconnect_success = handle_not_associated_reconnect_and_restart(
                                                dut_ip, user, password, term, term_arg, max_retries=2,
                                                filepath=filepath, mode_name=mode_name
                                            )
                                        finally:
                                            RECONNECTION_TRIGGERED.clear()
                                            RECONNECTION_IN_PROGRESS.release()
                                    else:
                                        log_print(f"[Monitor] Another monitor is already handling reconnection ({mode_name})")

                                    if attempted_reconnect:
                                        if reconnect_success:
                                            log_print(f"[Monitor] Reconnection SUCCESSFUL - wl status shows ASSOCIATED")
                                            log_print(f"[Monitor] Setting flag to RERUN test mode: {mode_name}")
                                            # Extract base mode name (remove _server or _client suffix)
                                            global RERUN_CURRENT_MODE, RERUN_MODE_NAME, RERUN_LOCK
                                            try:
                                                base_mode = mode_name.rsplit('_', 1)[0] if '_server' in mode_name or '_client' in mode_name else mode_name
                                            except Exception:
                                                base_mode = mode_name
                                            with RERUN_LOCK:
                                                RERUN_MODE_NAME = base_mode
                                                RERUN_CURRENT_MODE.set()
                                            log_print(f"[Monitor] Will rerun test mode: {base_mode}")
                                        else:
                                            log_print(f"[Monitor] Reconnection FAILED - NOT ASSOCIATED after 2 attempts")
                                            request_fatal_stop(
                                                f"RECONNECT_FAILED:{mode_name}",
                                                dut_ip,
                                                user,
                                                password,
                                                stop_event=stop_event,
                                            )
                                    
                                    # Exit monitoring loop
                                    break
                                else:
                                    # DUT is ASSOCIATED - run diagnostic ping and continue monitoring
                                    log_print(f"[Monitor] DUT is ASSOCIATED - running diagnostic ping ({mode_name})")
                                    
                                    # Get ping target
                                    ping_target = CONFIG.get("STATIC_TARGET", dut_ip)
                                    ping_cmd = f"ping {ping_target} -c 5"
                                    
                                    # Run ping as diagnostic (don't stop iperf regardless of result)
                                    try:
                                        log_print(f"[Monitor] Running: {ping_cmd}")
                                        ping_result = subprocess.run(
                                            ping_cmd,
                                            shell=True,
                                            capture_output=True,
                                            text=True,
                                            timeout=10
                                        )
                                        
                                        if ping_result.returncode == 0:
                                            log_print(f"[Monitor] Diagnostic ping SUCCESSFUL to {ping_target}")
                                        else:
                                            log_print(f"[Monitor] Diagnostic ping FAILED to {ping_target} (exit code: {ping_result.returncode})")
                                            if ping_result.stdout:
                                                log_print(f"[Monitor] Ping output: {ping_result.stdout[:200]}")
                                    except subprocess.TimeoutExpired:
                                        log_print(f"[Monitor] Diagnostic ping timed out")
                                    except Exception as e:
                                        log_print(f"[Monitor] Error running diagnostic ping: {e}")
                                    
                                    # Reset zero counters and continue monitoring
                                    log_print(f"[Monitor] Resetting zero counters - continuing monitoring")
                                    zero_start_time = None
                                    consecutive_zeros = 0
                            else:
                                log_print(f"[Monitor] FWID NOT found in wl ver output")
                                request_fatal_stop(f"FWID_NOT_FOUND:{mode_name}", dut_ip, user, password, stop_event=stop_event)
                                return
                        except subprocess.TimeoutExpired as e:
                            timeout_count += 1
                            log_print(f"[Monitor] Error running wl commands: {e} (timeout count: {timeout_count})")
                            if timeout_count >= 5:
                                log_print(f"[Monitor] DUT HANGED - NOT RESPONDING (5+ timeouts) - STOPPING TEST")
                                stop_event.set()
                                subprocess.run("pkill -9 iperf 2>/dev/null || true", shell=True)
                                subprocess.run("killall -9 iperf 2>/dev/null || true", shell=True)
                                break
                        except Exception as e:
                            log_print(f"[Monitor] Error running wl commands: {e}")
                else:
                    # Non-zero throughput detected
                    if consecutive_zeros > 0:
                        log_print(f"[Monitor] Non-zero throughput detected - resetting zero counter")
                        consecutive_zeros = 0
                        zero_start_time = None
    
    except Exception as e:
        log_print(f"[Monitor] Error monitoring file: {e}")
    
    log_print(f"[Monitor] Stopped monitoring {filepath}. Total zero detections: {zero_count}, wl ver runs: {wl_ver_count}, wl status runs: {wl_status_count}, wl command timeouts: {timeout_count}")




def main():
    if os.name == "nt":
        log_print("This launcher is intended to run on Linux with an X terminal emulator.")
        sys.exit(1)

    # Check if connection script argument provided (called from wrap_5g_2g.sh)
    global CONNECTION_SCRIPT
    global FATAL_STOP_REASON
    global RERUN_CURRENT_MODE, RERUN_MODE_NAME, RERUN_LOCK
    connection_type = "unknown"
    if len(sys.argv) > 1:
        connection_script = sys.argv[1]
        CONNECTION_SCRIPT = connection_script  # Set global for use in reconnection
        log_print(f"\n{'='*60}")
        log_print(f"Running with connection script: {connection_script}")
        if "2g" in connection_script.lower():
            connection_type = "2G"
        elif "5g" in connection_script.lower():
            connection_type = "5G"
        log_print(f"Connection type: {connection_type}")
        log_print(f"{'='*60}\n")
    else:
        log_print("No connection script argument provided, running standalone")
        log_print(f"Using default CONNECTION_SCRIPT: {CONNECTION_SCRIPT}")

    check_prereqs()
    
    # Pre-test check: Only ask for confirmation in standalone mode
    if connection_type == "unknown":
        log_print("\n" + "="*60)
        log_print(f"IMPORTANT: Please ensure {CONNECTION_SCRIPT} is present on the DUT")
        log_print("="*60)
        input("Press ENTER to continue with the test...")
        log_print()

    term, term_arg = find_terminal()
    if not term:
        log_print("No supported terminal emulator found. Install gnome-terminal, xterm or konsole.")
        sys.exit(1)

    # Get script directory
    here = os.path.dirname(os.path.abspath(__file__))

    # Detect which .sh file launched this Python process
    global CALLER_SCRIPT
    CALLER_SCRIPT = _detect_caller_script(here)
    if CALLER_SCRIPT:
        log_print(f"Detected caller script: {os.path.basename(CALLER_SCRIPT)}")
    else:
        log_print("Could not detect caller script (will search all .sh files if needed)")

    # Get custom output name from config
    output_name = CONFIG.get("OUTPUT_NAME", "iperf_test")
    
    # Create output folder using OUTPUT_NAME
    if connection_type != "unknown":
        # Called from wrapper - use OUTPUT_NAME folder (wrapper will rename it)
        gen_dir = os.path.join(here, output_name)
        log_print(f"Running for {connection_type} connection - using: {gen_dir}")
    else:
        # Standalone mode - use timestamped subfolder
        gen_base_dir = os.path.join(here, output_name)
        os.makedirs(gen_base_dir, exist_ok=True)
        run_timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        output_folder_name = f"{output_name}_{run_timestamp}"
        gen_dir = os.path.join(gen_base_dir, output_folder_name)
        log_print(f"Standalone mode - using: {gen_dir}")
    
    os.makedirs(gen_dir, exist_ok=True)
    
    # Create logs subfolder
    logs_dir = os.path.join(gen_dir, "logs")
    os.makedirs(logs_dir, exist_ok=True)
    
    # Open monitor log file
    global LOG_FILE
    monitor_log_path = os.path.join(gen_dir, "monitor_logs.txt")
    try:
        LOG_FILE = open(monitor_log_path, 'w', buffering=1)  # Line buffered
        log_print(f"Monitor logs will be saved to: {monitor_log_path}")
    except Exception as e:
        log_print(f"Warning: Could not open monitor log file: {e}")
        LOG_FILE = None
    
    log_print(f"Output folder created: {gen_dir}")
    log_print(f"Logs folder created: {logs_dir}")

    dut = CONFIG.get("DUTS_IP")
    user = CONFIG.get("DUTS_USER", "root")
    password = CONFIG.get("DUTS_PASSWORD", "")
    # stdbuf forces line-buffered output for local iperf piped through tee.
    # Without this, iperf's stdio block-buffer (~8 KB) delays output ~2 min,
    # causing the 20-second startup check to see an empty file and stop the test.
    _stdbuf = "stdbuf -oL " if shutil.which("stdbuf") else ""

    # Build ssh invocation helper
    def remote_invoke(cmd, pty=False):
        # SSH uses DUTS_IP (dut variable) while iperf client uses STATIC_TARGET (if set)
        # pty=True adds -t to allocate a remote pseudo-terminal so iperf on the DUT
        # line-buffers its output instead of block-buffering through the SSH pipe.
        target_ssh = dut
        ssh_pty = "-t " if pty else ""
        if shutil.which("sshpass") and password:
            return f"sshpass -p {shlex.quote(password)} ssh {ssh_pty}-o StrictHostKeyChecking=no {user}@{target_ssh} '{cmd}'"
        else:
            return f"ssh {ssh_pty}-o StrictHostKeyChecking=no {user}@{target_ssh} '{cmd}'"

    term_name, term_arg = term, term_arg

    # Reset process-wide control flags for this invocation
    FATAL_STOP_EVENT.clear()
    RECONNECTION_TRIGGERED.clear()
    RERUN_CURRENT_MODE.clear()
    with FATAL_STOP_LOCK:
        FATAL_STOP_REASON = None

    # Build run list from CONFIG['MODE']
    # Acceptable forms:
    # - single string: 'tcp_rx'
    # - comma-separated string: 'tcp_tx,tcp_rx'
    # - list: ['tcp_tx','tcp_rx']
    # - special: 'all' -> runs all four modes
    requested_mode = CONFIG.get("MODE")
    runs = []
    if isinstance(requested_mode, list):
        runs = requested_mode
    else:
        # normalize to string
        try:
            rm = str(requested_mode).strip()
        except Exception:
            rm = ""

        if rm.lower() == "all":
            runs = ["tcp_rx", "tcp_tx", "udp_rx", "udp_tx"]
        elif "," in rm:
            runs = [m.strip() for m in rm.split(",") if m.strip()]
        elif rm:
            runs = [rm]
        else:
            runs = ["tcp_rx"]

    idx = 0
    while idx < len(runs):
        if FATAL_STOP_EVENT.is_set():
            log_print("[MAIN] Fatal stop is active - aborting remaining modes")
            break

        idx += 1  # Start from 1
        cur_mode = runs[idx - 1]

        # Pre-test cleanup from main launcher terminal before each mode starts
        try:
            pre_test_sleep = int(CONFIG.get("PRE_TEST_SLEEP", 20))
        except Exception:
            pre_test_sleep = 20
        pre_test_cleanup(sleep_seconds=pre_test_sleep, dut_ip=dut, user=user, password=password)

        server_cmd, client_cmd, server_on_remote = build_server_client_commands(mode=cur_mode)

        # Ensure stale reconnection marker is cleared before each mode
        RECONNECTION_TRIGGERED.clear()
        
        # Create separate output files for each mode
        server_out = os.path.join(gen_dir, f"server_{cur_mode}.txt")
        client_out = os.path.join(gen_dir, f"client_{cur_mode}.txt")

        log_print(f"Starting run {idx}/{len(runs)}: {cur_mode}")

        # Create stop event for this run
        stop_event = threading.Event()
        ping_lock = threading.Lock()  # Shared lock to ensure only one ping test runs at a time
        monitor_threads = []

        # Launch server and client for this mode
        if server_on_remote:
            # SSH to DUT and run server_cmd with proper flags
            # pty=True: allocates remote pty so iperf line-buffers (fixes startup check)
            remote_server_cmd = remote_invoke(server_cmd, pty=True)
            header = f"echo ''; echo '========================================'; echo 'MODE: {cur_mode.upper()} - RUN {idx}/{len(runs)}'; echo 'Time: '$(date); echo '========================================'; echo ''"
            shell_cmd = f"{header}; echo '=== Connecting to DUT via SSH ==='; echo 'Host: {dut}'; echo 'User: {user}'; echo ''; echo 'Killing any existing iperf...'; {remote_invoke('pkill -9 iperf 2>/dev/null || true; killall -9 iperf 2>/dev/null || true')}; echo ''; echo '=== Starting iperf server on DUT ==='; echo 'Command: {server_cmd}'; echo ''; {remote_server_cmd} 2>&1 | tee '{server_out}'"
            server_title = f"DUT server (SSH {dut}) - {cur_mode}"
            open_terminal_with_command(term_name, term_arg, shell_cmd, title=server_title)
            
            # Wait for server terminal to launch and SSH to establish
            log_print(f"Waiting 3 seconds for server terminal to launch and SSH connection to establish...")
            time.sleep(3)

            # Local client (waits for server to start)
            client_header = f"echo ''; echo '========================================'; echo 'MODE: {cur_mode.upper()} - RUN {idx}/{len(runs)}'; echo 'Time: '$(date); echo '========================================'; echo ''"
            # _stdbuf forces line-buffered output for local iperf piped through tee
            client_shell = f"{client_header}; echo '=== Waiting 5 seconds for server to be ready ==='; sleep 5; echo '=== Running iperf client ==='; echo '{client_cmd}'; echo ''; {_stdbuf}{client_cmd} 2>&1 | tee '{client_out}'"
            static_ip = CONFIG.get("STATIC_TARGET") or dut
            client_title = f"Local client -> {static_ip} - {cur_mode}"
            open_terminal_with_command(term_name, term_arg, client_shell, title=client_title)
            
            # Start monitoring threads for both server and client outputs
            server_monitor = threading.Thread(
                target=monitor_file_for_zero_throughput,
                args=(server_out, dut, user, password, stop_event, f"{cur_mode}_server", ping_lock, term_name, term_arg),
                daemon=True
            )
            client_monitor = threading.Thread(
                target=monitor_file_for_zero_throughput,
                args=(client_out, dut, user, password, stop_event, f"{cur_mode}_client", ping_lock, term_name, term_arg),
                daemon=True
            )
            server_monitor.start()
            client_monitor.start()
            monitor_threads = [server_monitor, client_monitor]
        else:
            # Local server
            header = f"echo ''; echo '========================================'; echo 'MODE: {cur_mode.upper()} - RUN {idx}/{len(runs)}'; echo 'Time: '$(date); echo '========================================'; echo ''"
            # _stdbuf forces line-buffered output for local iperf piped through tee
            server_shell = f"{header}; echo '=== Running local iperf server ==='; echo '{server_cmd}'; echo ''; {_stdbuf}{server_cmd} 2>&1 | tee '{server_out}'"
            server_title = f"Local iperf server - {cur_mode}"
            open_terminal_with_command(term_name, term_arg, server_shell, title=server_title)

            # Wait for server terminal to launch
            log_print(f"Waiting 2 seconds for local server to be ready...")
            time.sleep(2)
            
            # SSH to DUT and run client (waits for server to start)
            # pty=True: allocates remote pty so iperf line-buffers (fixes startup check)
            remote_client_cmd = remote_invoke(client_cmd, pty=True)
            client_header = f"echo ''; echo '========================================'; echo 'MODE: {cur_mode.upper()} - RUN {idx}/{len(runs)}'; echo 'Time: '$(date); echo '========================================'; echo ''"
            client_shell = f"{client_header}; echo '=== Waiting 3 seconds for server to be ready ==='; sleep 3; echo '=== SSH to DUT and run client ==='; echo '{remote_client_cmd}'; echo ''; {remote_client_cmd} 2>&1 | tee '{client_out}'"
            client_title = f"Remote client (SSH {dut}) -> local - {cur_mode}"
            open_terminal_with_command(term_name, term_arg, client_shell, title=client_title)
            
            # Start monitoring threads for both server and client outputs
            server_monitor = threading.Thread(
                target=monitor_file_for_zero_throughput,
                args=(server_out, dut, user, password, stop_event, f"{cur_mode}_server", ping_lock, term_name, term_arg),
                daemon=True
            )
            client_monitor = threading.Thread(
                target=monitor_file_for_zero_throughput,
                args=(client_out, dut, user, password, stop_event, f"{cur_mode}_client", ping_lock, term_name, term_arg),
                daemon=True
            )
            server_monitor.start()
            client_monitor.start()
            monitor_threads = [server_monitor, client_monitor]

        # Wait for the test to finish before starting next (duration + buffer)
        try:
            duration = int(CONFIG.get("TIME", 10))
        except Exception:
            duration = 10
        wait = duration + 6
        
        # Check periodically if stop_event was set by monitor
        log_print(f"Waiting {wait}s for mode {cur_mode} to complete (with monitoring)...")
        elapsed = 0
        while elapsed < wait:
            if FATAL_STOP_EVENT.is_set():
                log_print(f"[MAIN] Fatal stop requested during {cur_mode} - ending this run")
                stop_event.set()
                break

            if stop_event.is_set():
                log_print(f"[ALERT] Test {cur_mode} stopped early - monitoring detected failure (check logs above for details)")
                # Kill any remaining iperf processes - forceful
                subprocess.run("pkill -9 iperf 2>/dev/null || true", shell=True)
                subprocess.run("killall -9 iperf 2>/dev/null || true", shell=True)
                if shutil.which("sshpass") and password:
                    kill_remote = f"sshpass -p {shlex.quote(password)} ssh -o StrictHostKeyChecking=no {user}@{dut} 'pkill -9 iperf 2>/dev/null || true; killall -9 iperf 2>/dev/null || true'"
                else:
                    kill_remote = f"ssh -o StrictHostKeyChecking=no {user}@{dut} 'pkill -9 iperf 2>/dev/null || true; killall -9 iperf 2>/dev/null || true'"
                subprocess.run(kill_remote, shell=True)
                # Exit this test mode and continue to next
                log_print(f"[ALERT] Moving to next test (if any)")
                break
            time.sleep(1)
            elapsed += 1
        
        # Signal monitors to stop
        stop_event.set()
        
        # Wait for monitor threads to complete (especially important if reconnection is happening)
        log_print(f"[MAIN] Waiting for monitor threads to finish (includes reconnection if triggered)...")
        for monitor in monitor_threads:
            monitor.join(timeout=120)  # Wait up to 2 minutes for reconnection to complete
        log_print(f"[MAIN] All monitor threads finished")

        if FATAL_STOP_EVENT.is_set():
            log_print(f"[MAIN] Fatal stop detected after {cur_mode}, skipping remaining modes")
            break
        
        # Check if we need to rerun this test due to successful reconnection
        with RERUN_LOCK:
            if RERUN_CURRENT_MODE.is_set() and RERUN_MODE_NAME == cur_mode:
                log_print(f"\n{'='*60}")
                log_print(f"[MAIN] Reconnection successful - RERUNNING test mode: {cur_mode}")
                log_print(f"{'='*60}\n")
                # Clear the rerun flag
                RERUN_CURRENT_MODE.clear()
                RERUN_MODE_NAME = None
                # Decrement idx to rerun this test
                idx -= 1
                # Wait a bit before rerunning
                log_print(f"[MAIN] Waiting 5 seconds before rerunning {cur_mode}...")
                time.sleep(5)
                continue  # Go back to start of while loop to rerun

    # Final cleanup - ensure all iperf processes and terminals are closed
    log_print("\n" + "=" * 60)
    log_print("[CLEANUP] Final cleanup - closing all iperf processes and terminals")
    log_print("=" * 60)
    
    # Kill all iperf processes (local and remote) - forceful
    subprocess.run("pkill -9 iperf 2>/dev/null || true", shell=True)
    subprocess.run("killall -9 iperf 2>/dev/null || true", shell=True)
    
    # Kill iperf on DUT
    if dut and user:
        try:
            ssh_base = build_ssh_base(dut, user, password)
            subprocess.run(f"{ssh_base} 'pkill -9 iperf 2>/dev/null || true; killall -9 iperf 2>/dev/null || true'", shell=True, timeout=5)
            log_print("[CLEANUP] Remote DUT iperf processes killed")
        except Exception as e:
            log_print(f"[CLEANUP] Error killing remote iperf: {e}")
    
    log_print("[CLEANUP] All iperf processes terminated")
    log_print("[CLEANUP] Terminals should close automatically in 5 seconds")
    log_print("[CLEANUP] Waiting for terminals to close...")
    time.sleep(2)  # Give terminals a moment to detect process death and close
    
    # Close log file before exit
    if LOG_FILE:
        try:
            LOG_FILE.close()
        except Exception:
            pass
    
    if FATAL_STOP_EVENT.is_set():
        # Final cleanup before exiting on fatal error
        log_print("\n" + "=" * 60)
        log_print("[CLEANUP] Fatal error cleanup - closing all iperf processes and terminals")
        log_print("=" * 60)
        
        # Kill all iperf processes (local and remote) - forceful
        subprocess.run("pkill -9 iperf 2>/dev/null || true", shell=True)
        subprocess.run("killall -9 iperf 2>/dev/null || true", shell=True)
        
        # Kill iperf on DUT
        try:
            ssh_base = build_ssh_base(dut, user, password)
            subprocess.run(f"{ssh_base} 'pkill -9 iperf 2>/dev/null || true; killall -9 iperf 2>/dev/null || true'", shell=True, timeout=5)
        except Exception:
            pass
        
        log_print("[CLEANUP] Waiting for terminals to close...")
        time.sleep(2)  # Give terminals a moment to detect process death and close
        
        log_print("\n" + "=" * 60)
        log_print("[MAIN] Test terminated due to fatal condition")
        if FATAL_STOP_REASON:
            log_print(f"[MAIN] Reason: {FATAL_STOP_REASON}")
        log_print("=" * 60)
        log_print(f"Results (partial or complete) saved in:")
        log_print(f"  Folder: {gen_dir}")
        log_print(f"  Logs: logs/")
        log_print(f"  Monitor logs: monitor_logs.txt")
        sys.exit(1)

    log_print(f"All runs completed. Results saved in:")
    log_print(f"  Folder: {gen_dir}")
    if requested_mode == "all":
        log_print(f"  Files: server_tcp_rx.txt, client_tcp_rx.txt, server_tcp_tx.txt, client_tcp_tx.txt")
        log_print(f"         server_udp_rx.txt, client_udp_rx.txt, server_udp_tx.txt, client_udp_tx.txt")
    else:
        log_print(f"  Files: server_{requested_mode}.txt, client_{requested_mode}.txt")
    log_print(f"  Logs: logs/")
    log_print(f"  Monitor logs: monitor_logs.txt")
    
    # Clean exit - allows wrap_5g_2g.sh to continue
    log_print(f"\nTest completed successfully - exiting cleanly")
    sys.exit(0)


if __name__ == "__main__":
    main()
