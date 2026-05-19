#!/usr/bin/env python3
import os
import sys
import re
import time
import argparse
import subprocess
import logging
import threading
import concurrent.futures
from datetime import datetime
from typing import Dict, List

import paramiko

# --- DYNAMIC SCRIPT DIRECTORY ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

WORKSPACE_DIR = "/home/hpsroot/Arvind-SIT/vindaloo_stv/packages-katsu"
UNIDIAG_BIN = "/home/hpsroot/venv-katsu/bin/unidiag"
CONFIG_PATH = os.path.join(WORKSPACE_DIR, "config.yaml")

# Path to the STV YAML used by unidiag
STV_YAML_PATH = "/home/hpsroot/venv-katsu/lib/python3.12/site-packages/unidiag/config/katsu/stv.yaml"

# --- KATSU CPU LOGIN SETTINGS ---
KATSU_CPU_USERNAME = "root"
KATSU_CPU_PASSWORD = "admin@123"

# --- UNIDIAG STV COMMANDS ---
STV_COMMANDS = {
    "smoke_test": f"{UNIDIAG_BIN} -c {CONFIG_PATH} test_compute stv_test smoke_test",
    "device_info_check": f"{UNIDIAG_BIN} -c {CONFIG_PATH} test_compute stv_test device_info_check",
    "pcie_tree_check": f"{UNIDIAG_BIN} -c {CONFIG_PATH} test_compute stv_test pcie_tree_check",
    "sensor_temp": f"{UNIDIAG_BIN} -c {CONFIG_PATH} test_compute stv_test sensor_check temperature",
    "sensor_volt": f"{UNIDIAG_BIN} -c {CONFIG_PATH} test_compute stv_test sensor_check voltage",
    "sensor_curr": f"{UNIDIAG_BIN} -c {CONFIG_PATH} test_compute stv_test sensor_check current",
    "log_check": f"{UNIDIAG_BIN} -c {CONFIG_PATH} test_compute stv_test log_check",
    "pcie_aer": f"{UNIDIAG_BIN} -c {CONFIG_PATH} test_compute stv_test pcie_aer",
    "rni_link_check": f"{UNIDIAG_BIN} -c {CONFIG_PATH} test_compute stv_test rni_link_check",
}

# --- PARALLEL SMOKE TEST SETTINGS ---
SMOKE_TEST_CHIPS = list(range(8))
SMOKE_TEST_PARALLELISM = 4              # 4-way avoids the DMA/IOMMU contention hangs we saw at 8-way
SMOKE_TEST_SSH_TIMEOUT_S = 30
SMOKE_TEST_CHIP_TIMEOUT_S = 10 * 60     # paramiko-side ceiling per chip
SMOKE_TEST_REMOTE_TIMEOUT_S = 600       # Katsu-side `timeout(1)` wrapper deadline (seconds)
SMOKE_TEST_HEARTBEAT_S = 60             # emit a "still waiting on chips ..." line every N seconds

SMOKE_NEXUS_CMD_TEMPLATE = (
    f'timeout --kill-after=15s {SMOKE_TEST_REMOTE_TIMEOUT_S}s '
    'smoke_nexus --nocapture --test "" --skip :compute_die: '
    '--test-threads=1 -- --silicon-mode '
    '--device-instance chip_id:{chip_id}'
)

SMOKE_RESULT_RE = re.compile(
    r"test result:\s+(?P<status>ok|FAILED)\.\s+"
    r"(?P<passed>\d+)\s+passed;\s+"
    r"(?P<failed>\d+)\s+failed"
)

# Lock so each chip's full output block is contiguous in the main log
# even when several chips finish in the same scheduler tick.
_smoke_dump_lock = threading.Lock()

# --- LOGGING SETUP ---
log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
date_format = "%H:%M:%S"

logging.basicConfig(
    level=logging.INFO,
    format=log_format,
    datefmt=date_format,
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("PCIe-STV-Suite")

# Silence paramiko's chatty INFO-level transport messages
logging.getLogger("paramiko").setLevel(logging.WARNING)


def log_test_case_start(test_case_name: str) -> None:
    logger.info("=" * 70)
    logger.info(f"🚀 TEST CASE BEGIN: {test_case_name.upper()}")
    logger.info("=" * 70)


# --- YAML CHIP LIST UPDATER ---
def update_chip_list(chip_ids: List[int]) -> bool:
    if not os.path.exists(STV_YAML_PATH):
        logger.error(f"stv.yaml not found at: {STV_YAML_PATH}")
        return False

    try:
        with open(STV_YAML_PATH, "r") as f:
            lines = f.readlines()

        chips_str = ", ".join(str(c) for c in chip_ids)
        replaced = False
        new_lines = []

        for line in lines:
            stripped = line.lstrip()
            if stripped.startswith("chip_list:"):
                indent = line[: len(line) - len(stripped)]
                new_line = f'{indent}chip_list: [{chips_str}]  #List of Chip IDs to be test\n'
                new_lines.append(new_line)
                replaced = True
                logger.info(f"Updated chip_list in stv.yaml -> [{chips_str}]")
            else:
                new_lines.append(line)

        if not replaced:
            logger.error("chip_list field not found in stv.yaml; no changes made.")
            return False

        with open(STV_YAML_PATH, "w") as f:
            f.writelines(new_lines)

        return True
    except Exception as e:
        logger.error(f"Failed to update chip_list in stv.yaml: {e}")
        return False


def _read_smoke_expected_counts():
    """
    Extract expected_passed_count and expected_failed_count from the
    smoke_test block of stv.yaml. Falls back to (22, 0) per the current
    YAML contract if anything goes wrong.
    """
    default_passed, default_failed = 22, 0
    try:
        with open(STV_YAML_PATH, "r") as f:
            content = f.read()

        m = re.search(r"^smoke_test:\s*\n((?:[ \t]+.*\n)+)", content, re.MULTILINE)
        if not m:
            return default_passed, default_failed

        block = m.group(1)
        passed_m = re.search(r"expected_passed_count:\s*(\d+)", block)
        failed_m = re.search(r"expected_failed_count:\s*(\d+)", block)

        return (
            int(passed_m.group(1)) if passed_m else default_passed,
            int(failed_m.group(1)) if failed_m else default_failed,
        )
    except Exception as e:
        logger.warning(
            f"Could not read expected counts from {STV_YAML_PATH}: {e}; "
            f"using defaults ({default_passed} passed / {default_failed} failed)."
        )
        return default_passed, default_failed


# --- LOCAL ORCHESTRATOR ---
class LocalUnidiagRunner:
    """Executes unidiag commands directly from the local host server."""

    def update_config_ip(self, cpu_ip: str) -> bool:
        """Updates only the CPU_ssh IP, username, and password in local config.yaml."""
        yaml_path = CONFIG_PATH

        if not os.path.exists(yaml_path):
            logger.error(f"Config file not found at: {yaml_path}")
            return False

        logger.info(f"Synchronizing local config.yaml -> CPU_ssh Katsu CPU: {cpu_ip}...")
        logger.info('Updating CPU_ssh credentials -> Username: "root", Password: "admin@123"')

        try:
            with open(yaml_path, 'r') as f:
                lines = f.readlines()

            new_lines = []
            inside_cpu_ssh = False
            cpu_ssh_indent = None

            for line in lines:
                stripped = line.lstrip()
                current_indent = len(line) - len(stripped)

                if stripped.startswith("CPU_ssh:"):
                    inside_cpu_ssh = True
                    cpu_ssh_indent = current_indent
                    new_lines.append(line)
                    continue

                if inside_cpu_ssh:
                    if (
                        stripped
                        and not stripped.startswith("#")
                        and ":" in stripped
                        and current_indent <= cpu_ssh_indent
                    ):
                        inside_cpu_ssh = False
                        cpu_ssh_indent = None

                if inside_cpu_ssh:
                    key = stripped.split(":", 1)[0].strip()
                    indent = line[:current_indent]

                    if key == "Ip_address":
                        new_lines.append(f'{indent}Ip_address: "{cpu_ip}"\n')
                        continue

                    if key == "Username":
                        new_lines.append(f'{indent}Username: "{KATSU_CPU_USERNAME}"\n')
                        continue

                    if key == "Password":
                        new_lines.append(f'{indent}Password: "{KATSU_CPU_PASSWORD}"\n')
                        continue

                new_lines.append(line)

            with open(yaml_path, 'w') as f:
                f.writelines(new_lines)

            logger.info("✅ Local config.yaml CPU_ssh successfully synchronized.")
            return True

        except Exception as e:
            logger.error(f"Failed to update config.yaml CPU_ssh section: {e}")
            return False

    def run_command(self, cmd: str) -> str:
        katsu_lib_path = os.path.join(WORKSPACE_DIR, "pylib")
        full_cmd = f"export PYTHONPATH=$PYTHONPATH:{katsu_lib_path} && {cmd}"

        logger.info(f"> [LOCAL CMD]: {full_cmd}")
        try:
            result = subprocess.run(
                full_cmd,
                shell=True,
                cwd=WORKSPACE_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                executable="/bin/bash"
            )
            return result.stdout.strip()
        except Exception as e:
            logger.error(f"Failed to run subprocess for STV command: {e}")
            return f"ERROR: {e}"


# --- EXECUTION SUMMARY ---
class ExecutionSummary:
    def __init__(self) -> None:
        self.test_results: Dict[str, bool] = {}

    def record_test(self, test_name: str, passed: bool) -> None:
        self.test_results[test_name] = passed

    def print_summary(self) -> None:
        logger.info("=" * 75)
        logger.info("🚀 FINAL EXECUTION SUMMARY".center(75))
        logger.info("=" * 75)

        if not self.test_results:
            logger.info("  No tests executed.")
        for test, passed in self.test_results.items():
            icon = "✅ PASS" if passed else "❌ FAIL"
            logger.info(f"  {icon:<7} | {test}")
        logger.info("=" * 75)


# --- PARALLEL SMOKE TEST (paramiko, capped parallelism, atomic per-line dump) ---
def _run_smoke_one_chip(
    chip_id: int,
    katsu_ip: str,
    expected_passed: int,
    expected_failed: int,
):
    """
    SSH into the Katsu CPU and run smoke_nexus for one chip. Buffer all stdout/stderr
    in memory and return it; the caller is responsible for emitting the captured
    output to the main log in the as-completed order.
    """
    cmd = SMOKE_NEXUS_CMD_TEMPLATE.format(chip_id=chip_id)
    logger.info(f"[smoke chip {chip_id}] start")

    start = time.monotonic()
    exit_status = -1
    output_buf: List[str] = []

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        client.connect(
            hostname=katsu_ip,
            username=KATSU_CPU_USERNAME,
            password=KATSU_CPU_PASSWORD,
            timeout=SMOKE_TEST_SSH_TIMEOUT_S,
            look_for_keys=False,
            allow_agent=False,
        )

        transport = client.get_transport()
        if transport is not None:
            transport.set_keepalive(30)

        stdin, stdout, stderr = client.exec_command(
            cmd,
            timeout=SMOKE_TEST_CHIP_TIMEOUT_S,
            get_pty=False,
        )
        stdout.channel.set_combine_stderr(True)

        for line in iter(stdout.readline, ""):
            output_buf.append(line)

        exit_status = stdout.channel.recv_exit_status()

    except Exception as e:
        logger.error(f"[smoke chip {chip_id}] SSH/exec failure: {e}")
        output_buf.append(f"\n[wrapper-error] {e}\n")
    finally:
        try:
            client.close()
        except Exception:
            pass

    elapsed = time.monotonic() - start
    full_output = "".join(output_buf)
    summary_match = SMOKE_RESULT_RE.search(full_output)

    if summary_match:
        status_str = summary_match.group("status")
        actual_passed = int(summary_match.group("passed"))
        actual_failed = int(summary_match.group("failed"))
        contract_ok = (
            status_str == "ok"
            and actual_passed >= expected_passed
            and actual_failed == expected_failed
        )
        if contract_ok and actual_passed != expected_passed:
            output_buf.append(
                f"\n[wrapper-note] smoke_nexus reported {actual_passed} passed but "
                f"stv.yaml expects {expected_passed}. Accepting under '>=' rule. "
                f"Consider syncing expected_passed_count in {STV_YAML_PATH}.\n"
            )
            full_output = "".join(output_buf)
        summary_seen = True
    else:
        status_str = "missing"
        actual_passed = -1
        actual_failed = -1
        contract_ok = False
        summary_seen = False

    passed = (exit_status == 0) and contract_ok

    detail = {
        "chip_id": chip_id,
        "passed": passed,
        "exit_status": exit_status,
        "summary_seen": summary_seen,
        "status_str": status_str,
        "actual_passed": actual_passed,
        "actual_failed": actual_failed,
        "elapsed_s": elapsed,
        "output": full_output,
    }

    icon = "PASS" if passed else "FAIL"
    logger.info(
        f"[smoke chip {chip_id}] finished {icon} "
        f"rc={exit_status} summary={status_str} "
        f"{actual_passed}P/{actual_failed}F "
        f"elapsed={elapsed:.1f}s"
    )

    return chip_id, passed, detail


def _dump_chip_block(chip_id: int, detail: dict, expected_passed: int, expected_failed: int) -> None:
    """Emit one chip's smoke output as a contiguous, prefixed block under the lock."""
    icon = "PASS" if detail["passed"] else "FAIL"
    header = (
        f"===== CHIP {chip_id} {icon} | rc={detail['exit_status']} | "
        f"{detail['actual_passed']}P/{detail['actual_failed']}F "
        f"(expected {expected_passed}P/{expected_failed}F) | "
        f"elapsed={detail['elapsed_s']:.1f}s ====="
    )
    output_lines = detail["output"].splitlines()

    with _smoke_dump_lock:
        logger.info(header)
        for line in output_lines:
            logger.info(f"[chip {chip_id}] {line}")
        logger.info(f"===== CHIP {chip_id} END =====")


def execute_smoke_test_parallel(katsu_ip: str, summary: ExecutionSummary) -> None:
    expected_passed, expected_failed = _read_smoke_expected_counts()

    label = (
        f"STV Smoke Test (parallel via paramiko, {SMOKE_TEST_PARALLELISM} workers, "
        f"{len(SMOKE_TEST_CHIPS)} chips, expecting "
        f">= {expected_passed} passed / == {expected_failed} failed per chip)"
    )
    log_test_case_start(label)
    logger.info(f"YAML contract source: {STV_YAML_PATH}")

    overall_start = time.monotonic()
    per_chip: Dict[int, dict] = {}

    logger.info("#" * 70)
    logger.info("SMOKE TEST OUTPUT (each chip's lines are prefixed with [chip N])")
    logger.info("#" * 70)

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=SMOKE_TEST_PARALLELISM,
        thread_name_prefix="smoke",
    ) as pool:
        futures = {
            pool.submit(
                _run_smoke_one_chip,
                chip_id,
                katsu_ip,
                expected_passed,
                expected_failed,
            ): chip_id
            for chip_id in SMOKE_TEST_CHIPS
        }

        not_done = set(futures.keys())

        while not_done:
            done, not_done = concurrent.futures.wait(
                not_done,
                timeout=SMOKE_TEST_HEARTBEAT_S,
                return_when=concurrent.futures.FIRST_COMPLETED,
            )

            if not done:
                remaining_chips = sorted(futures[f] for f in not_done)
                elapsed = time.monotonic() - overall_start
                logger.info(
                    f"[smoke heartbeat] still waiting on chips {remaining_chips} "
                    f"after {elapsed:.0f}s"
                )
                continue

            for fut in done:
                chip_id, _passed, detail = fut.result()
                per_chip[chip_id] = detail
                _dump_chip_block(chip_id, detail, expected_passed, expected_failed)

    overall_elapsed = time.monotonic() - overall_start

    for chip_id in sorted(per_chip.keys()):
        summary.record_test(
            f"STV Smoke Test - Chip {chip_id}",
            per_chip[chip_id]["passed"],
        )

    passing_chips = sum(1 for d in per_chip.values() if d["passed"])
    total_chips = len(SMOKE_TEST_CHIPS)
    aggregate_passed = passing_chips == total_chips
    summary.record_test("STV Smoke Test (aggregate)", aggregate_passed)

    logger.info("#" * 70)
    logger.info(
        f"Smoke parallel batch complete: {passing_chips}/{total_chips} chips passed "
        f"in {overall_elapsed:.1f}s (aggregate={'PASS' if aggregate_passed else 'FAIL'})"
    )
    logger.info("#" * 70)


def _cleanup_remote_smoke_nexus(katsu_ip: str) -> None:
    """
    Best-effort: kill any leftover smoke_nexus processes on Katsu. Catches the
    case where the wrapper was Ctrl-C'd mid-run and SSH-launched processes were
    left orphaned. Safe to call when nothing is running (pkill returns 1, ignored).
    """
    try:
        cleanup_client = paramiko.SSHClient()
        cleanup_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        cleanup_client.connect(
            hostname=katsu_ip,
            username=KATSU_CPU_USERNAME,
            password=KATSU_CPU_PASSWORD,
            timeout=10,
            look_for_keys=False,
            allow_agent=False,
        )
        cleanup_client.exec_command(
            "pkill -TERM smoke_nexus 2>/dev/null; sleep 2; "
            "pkill -KILL smoke_nexus 2>/dev/null; true",
            timeout=15,
        )
        cleanup_client.close()
        logger.info("Best-effort smoke_nexus cleanup sent to Katsu.")
    except Exception as e:
        logger.warning(f"Smoke cleanup pass failed (harmless): {e}")


# --- RNI LINK CHECK PER CHIP 0..7 ---
def execute_rni_link_checks_per_chip(runner: LocalUnidiagRunner, summary: ExecutionSummary):
    cmd = STV_COMMANDS["rni_link_check"]

    for chip_id in range(8):
        if not update_chip_list([chip_id]):
            logger.error(f"Skipping RNI Link Check for chip {chip_id}: failed to update chip_list.")
            summary.record_test(f"RNI Link Check - Chip {chip_id}", False)
            continue

        test_name = f"RNI Link Check - Chip {chip_id}"
        log_test_case_start(test_name)
        out = runner.run_command(cmd)
        logger.info(f"--- Console Output ---\n{out}\n{'-'*40}")

        passed = "[PASS]" in out and "[FAIL]" not in out
        summary.record_test(test_name, passed)

        if not passed:
            logger.error(f"{test_name} reported a failure or error.")


# --- MAIN RUNNER ---
def execute_stv_tests(
    runner: LocalUnidiagRunner,
    summary: ExecutionSummary,
    katsu_ip: str,
) -> None:
    test_mapping = {
        "STV Device Info Check": STV_COMMANDS["device_info_check"],
        "STV Smoke Test":        STV_COMMANDS["smoke_test"],
        "STV PCIe Tree Check":   STV_COMMANDS["pcie_tree_check"],
        "STV Temperature Check": STV_COMMANDS["sensor_temp"],
        "STV Voltage Check":     STV_COMMANDS["sensor_volt"],
        "STV Current Check":     STV_COMMANDS["sensor_curr"],
        "STV Log Check":         STV_COMMANDS["log_check"],
        "RNI Link Check":        STV_COMMANDS["rni_link_check"],
        "PCIe AER Check":        STV_COMMANDS["pcie_aer"]
    }

    for test_name, command in test_mapping.items():
        if test_name == "RNI Link Check":
            execute_rni_link_checks_per_chip(runner, summary)
            continue

        if test_name == "STV Smoke Test":
            execute_smoke_test_parallel(katsu_ip, summary)
            continue

        log_test_case_start(test_name)
        out = runner.run_command(command)
        logger.info(f"--- Console Output ---\n{out}\n{'-'*40}")

        passed = "[PASS]" in out and "[FAIL]" not in out
        summary.record_test(test_name, passed)

        if not passed:
            logger.error(f"{test_name} reported a failure or error.")


def main():
    parser = argparse.ArgumentParser(description="Host Server -> Katsu PCIe/STV Validation Suite")
    parser.add_argument("--katsu-cpu-ip", required=True, help="IP Address of the target Katsu CPU")
    parser.add_argument("--results-dir", default=os.path.join(SCRIPT_DIR, "results_pcie"), help="Base directory to store results")
    args = parser.parse_args()

    cpu_ip = args.katsu_cpu_ip
    base_results_dir = os.path.abspath(args.results_dir)
    os.makedirs(base_results_dir, exist_ok=True)

    summary = ExecutionSummary()
    runner = LocalUnidiagRunner()

    try:
        run_timestamp = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
        safe_ip_string = cpu_ip.replace('.', '_')
        run_dir_name = f"katsu_cpu_{safe_ip_string}_{run_timestamp}"

        dynamic_results_dir = os.path.join(base_results_dir, run_dir_name)
        os.makedirs(dynamic_results_dir, exist_ok=True)

        log_file_path = os.path.join(dynamic_results_dir, "pcie_stv_run.log")
        file_handler = logging.FileHandler(log_file_path)
        file_handler.setFormatter(logging.Formatter(log_format, datefmt=date_format))
        logger.addHandler(file_handler)

        logger.info(f"Logging initialized. Output directory: {dynamic_results_dir}")

        if not runner.update_config_ip(cpu_ip):
            logger.error("Aborting suite: Could not update config.yaml.")
            sys.exit(1)

        execute_stv_tests(runner, summary, cpu_ip)

    except KeyboardInterrupt:
        logger.warning("Execution interrupted by user.")
    except Exception as e:
        logger.error(f"Critical suite failure: {e}", exc_info=True)
        sys.exit(1)
    finally:
        _cleanup_remote_smoke_nexus(cpu_ip)

        if not update_chip_list(list(range(8))):
            logger.error("Failed to restore chip_list to default [0..7].")
        else:
            logger.info("Restored chip_list in stv.yaml to default [0, 1, 2, 3, 4, 5, 6, 7].")

        summary.print_summary()
        logger.info("Suite Execution Complete.")


if __name__ == "__main__":
    main()
