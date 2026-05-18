#!/usr/bin/env python3
import os
import sys
import argparse
import subprocess
import logging
from datetime import datetime
from typing import Dict, List

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

def log_test_case_start(test_case_name: str) -> None:
    logger.info(f"\n{'='*70}")
    logger.info(f"🚀 TEST CASE BEGIN: {test_case_name.upper()}")
    logger.info(f"{'='*70}")

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
        logger.info("\n" + "="*75)
        logger.info(f"{'🚀 FINAL EXECUTION SUMMARY':^75}")
        logger.info("="*75)

        if not self.test_results:
            logger.info("  No tests executed.")
        for test, passed in self.test_results.items():
            icon = "✅ PASS" if passed else "❌ FAIL"
            logger.info(f"  {icon:<7} | {test}")
        logger.info("="*75 + "\n")

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
def execute_stv_tests(runner: LocalUnidiagRunner, summary: ExecutionSummary):
    test_mapping = {
        "STV Device Info Check": STV_COMMANDS["device_info_check"],
        "STV Smoke Test": STV_COMMANDS["smoke_test"],
        "STV PCIe Tree Check": STV_COMMANDS["pcie_tree_check"],
        "STV Temperature Check": STV_COMMANDS["sensor_temp"],
        "STV Voltage Check": STV_COMMANDS["sensor_volt"],
        "STV Current Check": STV_COMMANDS["sensor_curr"],
        "STV Log Check": STV_COMMANDS["log_check"],
        "RNI Link Check": STV_COMMANDS["rni_link_check"],
        "PCIe AER Check": STV_COMMANDS["pcie_aer"]
    }

    for test_name, command in test_mapping.items():
        if test_name == "RNI Link Check":
            execute_rni_link_checks_per_chip(runner, summary)
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

        execute_stv_tests(runner, summary)

    except KeyboardInterrupt:
        logger.warning("Execution interrupted by user.")
    except Exception as e:
        logger.error(f"Critical suite failure: {e}", exc_info=True)
        sys.exit(1)
    finally:
        if not update_chip_list(list(range(8))):
            logger.error("Failed to restore chip_list to default [0..7].")
        else:
            logger.info("Restored chip_list in stv.yaml to default [0, 1, 2, 3, 4, 5, 6, 7].")

        summary.print_summary()
        logger.info("Suite Execution Complete.")

if __name__ == "__main__":
    main()
