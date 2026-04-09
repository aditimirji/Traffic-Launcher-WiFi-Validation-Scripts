# Traffic-Launcher-WiFi-Validation-Scripts
Traffic Launcher 1.3 is designed for automated WiFi throughput testing and diagnostics. It runs iperf traffic tests while continuously monitoring DUT connection health, automatically handling disconnection events, and generating comprehensive test reports.
# Traffic Launcher 1.3

A comprehensive automated WiFi traffic testing framework for wireless DUT (Device Under Test) performance validation. This tool orchestrates iperf traffic tests across multiple bands (5G/2G), monitors connection stability, and provides detailed diagnostic outputs.

---

## 📋 Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Configuration](#configuration)
- [Usage Workflow](#usage-workflow)
- [File Structure](#file-structure)
- [Output Structure](#output-structure)
- [Test Modes](#test-modes)
- [Monitoring & Recovery](#monitoring--recovery)
- [Troubleshooting](#troubleshooting)

---

## 🎯 Overview

Traffic Launcher 1.3 is designed for automated WiFi throughput testing and diagnostics. It runs iperf traffic tests while continuously monitoring DUT connection health, automatically handling disconnection events, and generating comprehensive test reports.

### Key Capabilities

- **Multi-Mode Testing**: TCP RX/TX and UDP RX/TX traffic patterns
- **Band Switching**: Automated 5G → 2G sequential testing with separate result folders
- **Real-Time Monitoring**: Zero-throughput detection with diagnostic command execution
- **Auto-Recovery**: Automatic reconnection on "NOT ASSOCIATED" events
- **DLS Support**: Dynamic Link Switching between 5GHz and 2.4GHz bands
- **Comprehensive Logging**: Timestamped outputs with pre/post-traffic diagnostics

---

## ✨ Features

### Traffic Testing
- ✅ **TCP RX**: DUT acts as server (receives TCP traffic)
- ✅ **TCP TX**: DUT acts as client (transmits TCP traffic)
- ✅ **UDP RX**: DUT receives UDP traffic at specified rate
- ✅ **UDP TX**: DUT transmits UDP traffic at specified rate
- ✅ Configurable window size, test duration, and UDP rate

### Monitoring
- 🔍 **Zero-Throughput Detection**: Detects 10 seconds of zero traffic
- 🔍 **Startup Validation**: Ensures traffic starts within 20 seconds
- 🔍 **FWID Verification**: Runs `wl ver` to check firmware presence
- 🔍 **Association Check**: Runs `wl status` to verify connection state
- 🔍 **Ping Validation**: Tests network reachability when throughput drops

### Diagnostics
- 📊 Pre-traffic scan results (wl scan, scanresults)
- 📊 Post-traffic scan results
- 📊 Periodic wl counters (optional)
- 📊 Connection logs with timestamps
- 📊 Failed test markers with preserved outputs

### Recovery
- 🔄 Automatic reconnection on "NOT ASSOCIATED"
- 🔄 Multiple retry attempts (configurable)
- 🔄 Graceful cleanup of iperf processes
- 🔄 Test resume or skip on recovery failure

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Traffic Launcher 1.3                      │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌───────────────┐      ┌──────────────────┐                │
│  │  Wrapper      │      │  Python Launcher  │                │
│  │  Scripts      │─────▶│  (main.py, etc.) │                │
│  │               │      │                   │                │
│  │ - wrap_5g_2g  │      │  - Traffic setup  │                │
│  │   _ml.sh      │      │  - Mode execution │                │
│  │ - wrap_5g_2g  │      │  - Monitoring     │                │
│  │   .sh         │      └────────┬──────────┘                │
│  └───────────────┘               │                           │
│         │                        │                           │
│         ▼                        ▼                           │
│  ┌─────────────────────────────────────────┐                │
│  │      Connection Scripts (SSH)            │                │
│  │                                          │                │
│  │  - 5g_ml_connect.sh / 5g_sl_connect.sh  │                │
│  │  - 2g_ml_connect.sh / 2g_sl_connect.sh  │                │
│  │  - WPA3 variants                        │                │
│  └──────────────┬───────────────────────────┘                │
│                 │                                            │
└─────────────────┼────────────────────────────────────────────┘
                  ▼
         ┌─────────────────┐
         │   DUT (Remote)   │
         │  172.16.10.25    │
         │                  │
         │  ┌────────────┐  │
         │  │ Management │  │ SSH (port 22)
         │  │ Plane IP   │◀─┼─────────────
         │  └────────────┘  │
         │                  │
         │  ┌────────────┐  │
         │  │ Data Plane │  │ iperf traffic
         │  │ IP (.50.25)│◀─┼─────────────
         │  └────────────┘  │
         └─────────────────┘
```

---

## 📦 Prerequisites

### Required Software
- **Linux OS** (tested on Ubuntu/Debian)
- **Python 3.6+**
- **iperf or iperf3** (configurable in CONFIG)
- **ssh** (OpenSSH client)
- **sshpass** (recommended for password authentication)
- **plink** (PuTTY Link for Windows-style SSH)
- **Terminal emulator**: gnome-terminal, xfce4-terminal, konsole, xterm, or lxterminal

### Network Setup
```
┌──────────────┐                    ┌──────────────┐
│   Test PC    │                    │     DUT      │
│              │                    │              │
│ Management:  │◄──SSH (port 22)───▶│ Management:  │
│ 172.16.10.x  │                    │ 172.16.10.25 │
│              │                    │              │
│ Data Plane:  │◄──iperf traffic───▶│ Data Plane:  │
│ 192.168.50.30│                    │ 192.168.50.25│
└──────────────┘                    └──────────────┘
```

### DUT Requirements
- SSH access enabled (root user)
- Broadcom WiFi driver with `wl` utility
- iperf server/client capability
- Network interfaces configured on data plane

---

## ⚙️ Configuration

### Python Script Configuration

Edit the `CONFIG` dictionary in your chosen Python script:

```python
CONFIG = {
    # Network Configuration
    "DUTS_IP": "172.16.10.25",          # DUT management IP (SSH)
    "DUTS_USER": "root",                # SSH username
    "DUTS_PASSWORD": "hrun*10",         # SSH password
    "STATIC_TARGET": "192.168.50.25",   # DUT data plane IP (iperf)
    "LOCAL_IP": "192.168.50.30",        # Local data plane IP (iperf)
    
    # Traffic Parameters
    "WINDOW": "60K",                    # TCP window size
    "TIME": "1800",                     # Test duration (seconds)
    "UDP_RATE": "35M",                  # UDP bitrate
    "IPERF_BIN": "iperf",              # iperf or iperf3
    
    # Test Configuration
    "OUTPUT_NAME": "my_test_results",   # Output folder name
    "MODE": "tcp_tx, udp_rx",          # Test modes (comma-separated)
    "PRE_TEST_SLEEP": "20",            # Cleanup wait time (seconds)
    
    # Optional Features
    "ENABLE_WL_COUNTERS": True,        # Periodic wl counters
    "ENABLE_DLS_TOGGLE": False,        # Dynamic Link Switching
    "DLS_TOGGLE_INTERVAL": 60,         # DLS interval (seconds)
}
```

### Script Selection Guide

| Script | Use Case |
|--------|----------|
| **main.py** | Standard tests with full monitoring and wl counters |
| **new.py** | Enhanced diagnostics with pre/post-traffic scans |
| **open_air_test.py** | Open-air testing (different DUT IP: .22) |
| **switch_no_wl.py** | Tests without wl counter calls (DLS toggle focus) |

### Wrapper Script Selection

| Wrapper | Connection Type | Use Case |
|---------|----------------|----------|
| **wrap_5g_2g.sh** | Single-Link (SL) | 5G SL → 2G SL sequential testing |
| **wrap_5g_2g_ml.sh** | Multi-Link (ML) | 5G ML → 2G ML sequential testing |

---

## 🚀 Usage Workflow

### Method 1: Direct Python Execution (Single Band)

```bash
# Step 1: Navigate to project directory
cd ~/Traffic_Launcher1.3

# Step 2: Edit configuration in Python script
nano main.py  # Adjust CONFIG dictionary

# Step 3: Run with connection script argument
python3 main.py /root/connection_script/5g_sl_connect.sh
```

**Workflow:**
```
┌────────┐    ┌──────────────┐    ┌─────────────┐    ┌──────────┐
│ Start  │───▶│ Pre-cleanup  │───▶│ Run Mode 1  │───▶│ Monitor  │
└────────┘    │ (pkill iperf)│    │  (tcp_tx)   │    │ (0 Mbps) │
              └──────────────┘    └─────────────┘    └────┬─────┘
                                          │                 │
                      ┌───────────────────┘                 │
                      ▼                                     ▼
              ┌─────────────┐                    ┌──────────────────┐
              │ Run Mode 2  │                    │ If NOT ASSOCIATED│
              │  (udp_rx)   │                    │  → Reconnect     │
              └──────┬──────┘                    └──────────────────┘
                     │
                     ▼
              ┌─────────────┐
              │  Complete   │
              │ (Timestamped│
              │  Results)   │
              └─────────────┘
```

### Method 2: Wrapper Script Execution (Sequential 5G → 2G)

```bash
# Step 1: Navigate to project directory
cd ~/Traffic_Launcher1.3

# Step 2: Execute wrapper script
bash wrap_5g_2g_ml.sh
# or
bash wrap_5g_2g.sh
```

**Wrapper Workflow:**
```
┌─────────────────────────────────────────────────────────────────┐
│                     WRAPPER SCRIPT START                         │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                ┌───────────▼───────────┐
                │ 1. SCP Connection     │
                │    Scripts to DUT     │
                └───────────┬───────────┘
                            │
        ┌───────────────────┴───────────────────┐
        │                                       │
┌───────▼────────┐                    ┌────────▼────────┐
│  5G PHASE      │                    │  2G PHASE       │
│                │                    │                 │
│ ┌────────────┐ │                    │ ┌────────────┐  │
│ │ Connect 5G │ │                    │ │ Connect 2G │  │
│ │  (plink)   │ │                    │ │  (plink)   │  │
│ └──────┬─────┘ │                    │ └──────┬─────┘  │
│        │       │                    │        │        │
│ ┌──────▼─────┐ │                    │ ┌──────▼─────┐  │
│ │Run Python  │ │                    │ │Run Python  │  │
│ │ (main.py)  │ │                    │ │ (main.py)  │  │
│ └──────┬─────┘ │                    │ └──────┬─────┘  │
│        │       │                    │        │        │
│ ┌──────▼─────┐ │                    │ ┌──────▼─────┐  │
│ │ Rename     │ │                    │ │ Rename     │  │
│ │ folder     │ │                    │ │ folder     │  │
│ │ *_5G_ML    │ │                    │ │ *_2G_ML    │  │
│ └────────────┘ │                    │ └────────────┘  │
└────────────────┘                    └─────────────────┘
        │                                      │
        └──────────────┬───────────────────────┘
                       │
               ┌───────▼────────┐
               │ TWO SEPARATE   │
               │ RESULT FOLDERS │
               └────────────────┘
```

---

## 📁 File Structure

```
Traffic_Launcher1.3/
│
├── README.md                    # This file
│
├── Python Scripts (Launchers)
│   ├── main.py                  # Standard launcher with wl counters
│   ├── new.py                   # Launcher with scan diagnostics
│   ├── open_air_test.py         # Open-air testing variant
│   └── switch_no_wl.py          # Launcher without wl counters (DLS focus)
│
├── Wrapper Scripts
│   ├── wrap_5g_2g_ml.sh         # Multi-link 5G+2G sequential wrapper
│   └── wrap_5g_2g.sh            # Single-link 5G+2G sequential wrapper
│
└── connection_script/           # Connection & setup scripts
    ├── 5g_ml_connect.sh         # 5GHz multi-link connection
    ├── 5g_sl_connect.sh         # 5GHz single-link connection
    ├── 2g_ml_connect.sh         # 2.4GHz multi-link connection
    ├── 2g_sl_connect.sh         # 2.4GHz single-link connection
    ├── 5g_wpa3_connect.sh       # 5GHz WPA3 connection
    ├── 2g_wpa3_connect.sh       # 2.4GHz WPA3 connection
    ├── load_fmac.sh             # Load FMAC driver
    ├── load_fmac_rram.sh        # Load FMAC with RRAM
    ├── load_fmac_traffic.sh     # Load FMAC for traffic testing
    ├── traffic_pre_req.sh       # Traffic prerequisites
    └── tuning.sh                # System tuning parameters
```

---

## 📊 Output Structure

### Single Test Execution

```
my_test_results/
├── server_tcp_tx.txt           # Server side output
├── client_tcp_tx.txt           # Client side output
├── server_udp_rx.txt
├── client_udp_rx.txt
├── monitor_log.txt             # Real-time monitoring log
└── logs/
    ├── counters_tcp_tx_20260409_143022.txt
    ├── counters_udp_rx_20260409_150534.txt
    ├── pre_traffic_tcp_tx_20260409_143015.txt
    ├── post_traffic_tcp_tx_20260409_145015.txt
    └── FAILED_tcp_rx_20260409_151203.txt  # (if test failed)
```

### Wrapper Script Execution (Sequential 5G → 2G)

```
my_test_results_09-04-2026_14-30-22_5G_ML/
├── server_tcp_tx.txt
├── client_tcp_tx.txt
├── load_connection_5G_ML.txt   # Connection log
├── monitor_log.txt
└── logs/
    └── ...

my_test_results_09-04-2026_15-05-34_2G_ML/
├── server_tcp_tx.txt
├── client_tcp_tx.txt
├── load_connection_2G_ML.txt   # Connection log
├── monitor_log.txt
└── logs/
    └── ...
```

### Log File Contents

#### monitor_log.txt
- Real-time throughput monitoring events
- Zero-throughput detection triggers
- wl ver / wl status command outputs
- Reconnection attempts and results
- DLS toggle events (if enabled)
- Test start/stop timestamps

#### counters_*.txt
- Periodic wl counters snapshots
- Timestamp for each counter collection
- Full driver statistics

#### pre_traffic_*.txt / post_traffic_*.txt
- wl scansuppress 0
- wl scan results
- wl status before/after traffic
- Network scan diagnostics

---

## 🎯 Test Modes

### Traffic Direction

| Mode | Description | DUT Role | iperf Command |
|------|-------------|----------|---------------|
| **tcp_rx** | DUT receives TCP | Server | `iperf -s` on DUT, `-c` on PC |
| **tcp_tx** | DUT transmits TCP | Client | `iperf -s` on PC, `-c` on DUT |
| **udp_rx** | DUT receives UDP | Server | `iperf -s -u` on DUT, `-c -u` on PC |
| **udp_tx** | DUT transmits UDP | Client | `iperf -s -u` on PC, `-c -u` on DUT |

### Multi-Mode Configuration

```python
# Single mode
"MODE": "tcp_tx"

# Multiple modes (comma-separated, runs sequentially)
"MODE": "tcp_tx, udp_rx, tcp_rx, udp_tx"

# All modes
"MODE": "all"  # Expands to: tcp_rx, tcp_tx, udp_rx, udp_tx
```

**Execution Order**: Tests run left-to-right with pre-test cleanup between each mode.

---

## 🔍 Monitoring & Recovery

### Startup Validation (First 20 Seconds)

```
Traffic Start
     │
     ▼
┌─────────────────────┐
│ Wait for non-zero   │
│ throughput (20s max)│
└──────────┬──────────┘
           │
       ┌───┴───┐
       │       │
   Traffic  No Traffic
   Detected  (20s)
       │       │
       ▼       ▼
   Continue  ┌────────────┐
   Test      │ Run wl ver │
             └──────┬─────┘
                    │
            ┌───────┴────────┐
            │                │
        FWID Found      No FWID
            │                │
            ▼                ▼
     ┌─────────────┐  ┌──────────┐
     │ Check wl    │  │ STOP TEST│
     │ status      │  │ (No FW)  │
     └──────┬──────┘  └──────────┘
            │
    ┌───────┴────────┐
    │                │
Associated    NOT ASSOCIATED
    │                │
    ▼                ▼
Continue      ┌──────────────┐
Test          │ STOP TEST    │
              │ (Reconnect   │
              │  needed)     │
              └──────────────┘
```

### Ongoing Monitoring (Every Second)

```
Monitor Loop
     │
     ▼
┌──────────────────┐
│ Read latest line │
│ Parse throughput │
└────────┬─────────┘
         │
    ┌────┴────┐
    │         │
Non-zero    Zero
    │         │
    ▼         ▼
Reset    Increment
Counter  Zero Counter
    │         │
    │    ┌────┴──────┐
    │    │           │
    │  <10 secs   10 secs
    │    │           │
    │    ▼           ▼
    │  Continue  ┌────────────┐
    │            │ Run wl ver │
    │            └──────┬─────┘
    │                   │
    │           ┌───────┴────────┐
    │           │                │
    │       FWID Found      No FWID
    │           │                │
    │           ▼                ▼
    │    ┌─────────────┐  ┌──────────┐
    │    │ Check wl    │  │ Run ping │
    │    │ status      │  │  test    │
    │    └──────┬──────┘  └─────┬────┘
    │           │               │
    │   ┌───────┴────────┐  ┌───┴────┐
    │   │                │  │        │
    │Associated   NOT     Ping   Ping
    │   │        ASSOC   OK     Fail
    │   │           │     │       │
    │   ▼           ▼     ▼       ▼
    │  Ping    ┌────────┐ Cont  STOP
    └─▶Test    │STOP &  │ Test  TEST
               │Reconn. │
               └────────┘
```

### Reconnection Process

```
NOT ASSOCIATED Detected
         │
         ▼
┌──────────────────┐
│ Kill all iperf   │
│ (local + remote) │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Run connection   │
│ script (plink)   │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Wait 10 seconds  │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Check wl status  │
└────────┬─────────┘
         │
    ┌────┴────┐
    │         │
Associated  Still NOT
    │       ASSOCIATED
    ▼           │
┌────────┐      ▼
│SUCCESS │  ┌─────────────┐
│ Resume │  │ Retry again │
│  test  │  │ (max 2x)    │
└────────┘  └──────┬──────┘
                   │
            ┌──────┴──────┐
            │             │
        Success      All Failed
            │             │
            ▼             ▼
        Resume      ┌──────────┐
         Test       │ SKIP     │
                    │ current  │
                    │ mode     │
                    └──────────┘
```

---

## 🛠️ Troubleshooting

### Common Issues

#### 1. "Terminal emulator not found"
**Cause**: No supported terminal installed  
**Solution**: Install a terminal emulator
```bash
sudo apt-get install gnome-terminal
# or
sudo apt-get install xfce4-terminal
```

#### 2. "iperf not found"
**Cause**: iperf not installed or not in PATH  
**Solution**: Install iperf
```bash
sudo apt-get install iperf3
# or for iperf2
sudo apt-get install iperf
```

#### 3. "sshpass not found" (Warning)
**Cause**: sshpass not installed (optional)  
**Solution**:
```bash
sudo apt-get install sshpass
```
Or use SSH keys for passwordless authentication

#### 4. SSH connection failures
**Cause**: Network unreachable or incorrect credentials  
**Solution**:
- Verify DUT IP: `ping 172.16.10.25`
- Test SSH manually: `ssh root@172.16.10.25`
- Check password in CONFIG
- Verify firewall rules

#### 5. "NOT ASSOCIATED" immediately after connection
**Cause**: Connection script failed or DUT not ready  
**Solution**:
- Check connection_script/*.sh files are correct
- Verify AP is broadcasting
- Check DUT WiFi interface is up: `ssh root@172.16.10.25 'ifconfig'`
- Review load_connection_*.txt logs

#### 6. Zero throughput but DUT is associated
**Cause**: Network routing or iperf configuration issue  
**Solution**:
- Verify data plane IPs: `ping 192.168.50.25`
- Check iperf is running: `ps aux | grep iperf`
- Verify firewall allows iperf port (5001/5201)
- Check UDP rate is achievable

#### 7. DLS toggle not working
**Cause**: ENABLE_DLS_TOGGLE is False or DUT doesn't support DLS  
**Solution**:
- Set `"ENABLE_DLS_TOGGLE": True` in CONFIG
- Verify DUT firmware supports `wl eht dls -f` command
- Check DLS_TOGGLE_INTERVAL is reasonable (>= 10 seconds)

#### 8. Tests marked as FAILED unexpectedly
**Cause**: Startup validation failure or persistent zero throughput  
**Solution**:
- Review monitor_log.txt for detailed timeline
- Check logs/FAILED_*.txt for failure reason
- Inspect preserved server/client outputs: *_FAILED_*.txt
- Verify network path and iperf parameters

---

## 📝 Advanced Configuration

### Custom Connection Scripts

Create your own connection script in `connection_script/`:

```bash
#!/bin/bash
# my_custom_connect.sh

# Load driver
sh /root/connection_script/load_fmac_traffic.sh

# Connect to AP
wl up
wl down
wl mpc 0
wl country ALL
wl chanspec 36/80
wl up
wl ssid "MyTestAP"
wl join "MyTestAP" amode open

# Wait and verify
sleep 5
wl status
```

Then use it:
```bash
python3 main.py /root/connection_script/my_custom_connect.sh
```

### DLS Toggle Timing

Adjust DLS toggle interval in CONFIG:
```python
"ENABLE_DLS_TOGGLE": True,
"DLS_TOGGLE_INTERVAL": 120,  # Switch bands every 2 minutes
```

### Custom Diagnostic Commands

Edit `run_wl_diagnostic_sequence()` function in Python scripts to add your own diagnostic commands.

---

## 📈 Performance Tips

1. **TCP Window Size**: Larger windows (60K-1M) generally improve TCP throughput
2. **UDP Rate**: Set below maximum achievable rate to avoid excessive packet loss
3. **Test Duration**: 1800s (30 min) recommended for stable averages
4. **Pre-test Sleep**: 20s recommended to ensure clean state between modes
5. **Concurrent Tests**: Run only one wrapper script at a time to avoid conflicts

---





## 🎓 Quick Start Example

```bash
# 1. Clone/extract to your test machine
cd ~/Traffic_Launcher1.3

# 2. Edit configuration
nano main.py
# Set DUTS_IP, STATIC_TARGET, LOCAL_IP, OUTPUT_NAME, MODE

# 3. Run single-band test
python3 main.py /root/connection_script/5g_sl_connect.sh

# 4. Or run sequential 5G→2G test
bash wrap_5g_2g.sh



**Output**: Timestamped folders with comprehensive traffic logs, monitoring events, and diagnostic outputs.

---

**Version**: 1.3  
**Last Updated**: April 2026  


