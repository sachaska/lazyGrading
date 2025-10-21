#!/usr/bin/env python3
"""
Test Script for Lab2: Bully Algorithm
Distributed Systems Class

This script:
1. Starts a GCD server
2. Launches multiple instances of each student's submission
3. Monitors their behavior and communication
4. Saves output logs for each node

Usage:
    python3 grade_bully.py [--students student1,student2,...] [--timeout 30]
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import threading
import signal
import socket
from pathlib import Path
from collections import defaultdict
from datetime import datetime

# Configuration
GCD_PORT = 50000
BASE_LISTEN_PORT = 60000
RUNTIME_SECONDS = 30
NUM_NODES = 4  # Number of nodes to simulate per student

# Validation constraints
VALID_SU_ID_MIN = 1000000
VALID_SU_ID_MAX = 9999999
VALID_DAYS_MIN = 0
VALID_DAYS_MAX = 365

# Test node configurations (days_to_birthday, su_id, month_day, month_day_year)
# These create different priorities for the Bully algorithm
# All values validated: su_id in [1000000, 9999999], days in [0, 365]
NODE_CONFIGS = [
    (100, 1234567, "01-29", "01-29-2026"),  # Priority 1 (lower days = higher priority in bully)
    (200, 2345678, "12-11", "12-11-2025"),  # Priority 2
    (300, 3456789, "07-09", "07-09-2026"),  # Priority 3
    (50, 4567890, "03-20", "03-20-2026"),   # Priority 4 (highest priority - will be leader)
]

def validate_node_config(days, su_id):
    """Validate that days and su_id are within acceptable ranges"""
    if not (VALID_DAYS_MIN <= days <= VALID_DAYS_MAX):
        raise ValueError(f"Days must be in range [{VALID_DAYS_MIN}, {VALID_DAYS_MAX}], got {days}")
    if not (VALID_SU_ID_MIN <= su_id <= VALID_SU_ID_MAX):
        raise ValueError(f"SU_ID must be in range [{VALID_SU_ID_MIN}, {VALID_SU_ID_MAX}], got {su_id}")
    return True

# Validate NODE_CONFIGS on module load
for days, su_id, _, _ in NODE_CONFIGS:
    validate_node_config(days, su_id)


def is_port_in_use(port):
    """Check if a port is already in use"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(('', port))
            return False
        except socket.error:
            return True


class ArgumentParser:
    """Parse different student argument formats"""

    @staticmethod
    def parse_template(template):
        """
        Parse a user-provided template string and return an argument generator function.

        Template variables:
        - {gcd_host} or {host}
        - {gcd_port} or {port}
        - {listen_port}
        - {su_id} or {suid}
        - {days} or {bday}
        - {month_day} (MM-DD format)
        - {month_day_year} (MM-DD-YYYY format)

        Example: "{gcd_host} {gcd_port} {listen_port} {su_id} {month_day}"
        """
        def generator(gcd_host, gcd_port, listen_port, su_id, bday, month_day, month_day_year):
            result = template
            # Replace all possible variables
            replacements = {
                '{gcd_host}': gcd_host,
                '{host}': gcd_host,
                '{gcd_port}': str(gcd_port),
                '{port}': str(gcd_port),
                '{listen_port}': str(listen_port),
                '{su_id}': str(su_id),
                '{suid}': str(su_id),
                '{days}': str(bday),
                '{bday}': str(bday),
                '{month_day}': month_day,
                '{month_day_year}': month_day_year,
            }
            for key, value in replacements.items():
                result = result.replace(key, value)

            # Split by whitespace and return as list
            return result.split()

        return generator

    @staticmethod
    def parse_usage_line(usage_text):
        """
        Extract argument pattern from usage text
        Returns a function that generates the correct arguments
        """
        if not usage_text:
            return None

        usage_lower = usage_text.lower()

        # Pattern matching for different argument formats
        patterns = [
            # Pattern: GCD_HOST GCD_PORT LISTEN_PORT SU_ID B-DAY (MM-DD or MM-DD-YYYY)
            (r'gcd.*host.*gcd.*port.*listen.*su.*id.*b.*day',
             lambda gcd_host, gcd_port, listen_port, su_id, bday, month_day, month_day_year:
                [gcd_host, str(gcd_port), str(listen_port), str(su_id), month_day_year]),

            # Pattern: SU_ID days_to_bday GCD_HOST GCD_PORT
            (r'su.*id.*day.*gcd.*host.*gcd.*port',
             lambda gcd_host, gcd_port, listen_port, su_id, bday, month_day, month_day_year:
                [str(su_id), str(bday), gcd_host, str(gcd_port)]),

            # Pattern: days_to_bday SU_ID GCD_HOST GCD_PORT
            (r'day.*su.*id.*host.*port',
             lambda gcd_host, gcd_port, listen_port, su_id, bday, month_day, month_day_year:
                [str(bday), str(su_id), gcd_host, str(gcd_port)]),

            # Pattern: GCD_HOST GCD_PORT SU_ID days_to_bday
            (r'gcd.*host.*gcd.*port.*su.*id.*day|gcd.*host.*gcd.*port.*student.*id.*birth',
             lambda gcd_host, gcd_port, listen_port, su_id, bday, month_day, month_day_year:
                [gcd_host, str(gcd_port), str(su_id), str(bday)]),

            # Pattern: GCD_HOST GCD_PORT days_to_bday SU_ID
            (r'gcd.*host.*gcd.*port.*day.*su.*id|gcd.*host.*gcd.*port.*n.*day.*student',
             lambda gcd_host, gcd_port, listen_port, su_id, bday, month_day, month_day_year:
                [gcd_host, str(gcd_port), str(bday), str(su_id)]),

            # Pattern: BDAY SUID HOST PORT
            (r'bday.*suid.*host.*port',
             lambda gcd_host, gcd_port, listen_port, su_id, bday, month_day, month_day_year:
                [str(bday), str(su_id), gcd_host, str(gcd_port)]),

            # Pattern: GCD_HOST GCD_PORT (minimal args)
            (r'gcd.*host.*gcd.*port$',
             lambda gcd_host, gcd_port, listen_port, su_id, bday, month_day, month_day_year:
                [gcd_host, str(gcd_port)]),

            # Pattern: SU_ID month day [gcd_host] [gcd_port]
            (r'su.*id.*month.*day',
             lambda gcd_host, gcd_port, listen_port, su_id, bday, month_day, month_day_year:
                [str(su_id)] + month_day.split('-') + [gcd_host, str(gcd_port)]),

            # Pattern: GCD_HOST GCD_PORT SU_ID MOM_BDAY_MM-DD or MM-DD-YYYY
            (r'gcd.*host.*gcd.*port.*su.*id.*mom.*bday|gcd.*host.*gcd.*port.*su.*id.*birthdate',
             lambda gcd_host, gcd_port, listen_port, su_id, bday, month_day, month_day_year:
                [gcd_host, str(gcd_port), str(su_id), month_day_year]),

            # Pattern: GCD_HOST GCD_PORT BIRTH_MONTH BIRTH_DAY SU_ID
            (r'gcd.*host.*gcd.*port.*birth.*month.*birth.*day.*su.*id',
             lambda gcd_host, gcd_port, listen_port, su_id, bday, month_day, month_day_year:
                [gcd_host, str(gcd_port)] + month_day.split('-') + [str(su_id)]),
        ]

        for pattern, arg_func in patterns:
            if re.search(pattern, usage_lower):
                return arg_func

        # Default fallback: assume GCD_HOST GCD_PORT days SU_ID
        return lambda gcd_host, gcd_port, listen_port, su_id, bday, month_day, month_day_year: \
            [gcd_host, str(gcd_port), str(bday), str(su_id)]


class StudentTester:
    """Tests a single student's submission and captures output"""

    def __init__(self, student_name, lab_file, arg_generator, student_dir, verbose=False):
        self.student_name = student_name
        self.lab_file = lab_file
        self.arg_generator = arg_generator
        self.student_dir = student_dir
        self.verbose = verbose
        self.processes = []
        self.outputs = defaultdict(list)
        self.errors = []
        self.log_files = {}

    def run_nodes(self, gcd_host, gcd_port, runtime):
        """Launch multiple node instances for this student"""
        for i, (days, su_id, month_day, month_day_year) in enumerate(NODE_CONFIGS):
            listen_port = BASE_LISTEN_PORT + i

            try:
                if self.arg_generator:
                    args = self.arg_generator(gcd_host, gcd_port, listen_port,
                                             su_id, days, month_day, month_day_year)
                else:
                    # Default argument order
                    args = [gcd_host, str(gcd_port), str(days), str(su_id)]

                # Setup log file for this node
                log_file_path = os.path.join(self.student_dir, f"node{i}.log")
                self.log_files[i] = open(log_file_path, 'w')

                # Write header to log file
                self.log_files[i].write(f"Node {i} Log\n")
                self.log_files[i].write(f"={'='*60}\n")
                self.log_files[i].write(f"Configuration:\n")
                self.log_files[i].write(f"  Days to birthday: {days}\n")
                self.log_files[i].write(f"  Student ID: {su_id}\n")
                self.log_files[i].write(f"  Month-Day: {month_day}\n")
                self.log_files[i].write(f"  Month-Day-Year: {month_day_year}\n")
                self.log_files[i].write(f"  Listen port: {listen_port}\n")
                self.log_files[i].write(f"Command: python3 {self.lab_file} {' '.join(args)}\n")
                self.log_files[i].write(f"={'='*60}\n\n")
                self.log_files[i].flush()

                # Use -u flag for unbuffered Python output
                cmd = ["python3", "-u", self.lab_file] + args

                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,  # Redirect stderr to stdout
                    text=True,
                    bufsize=0,  # Unbuffered
                    env={**os.environ, 'PYTHONUNBUFFERED': '1'}  # Disable Python buffering
                )

                self.processes.append(process)

                # Collect output in background thread
                threading.Thread(
                    target=self._collect_output,
                    args=(process, i),
                    daemon=True
                ).start()

                time.sleep(0.5)  # Stagger startup

            except Exception as e:
                error_msg = f"Failed to start node {i}: {str(e)}"
                self.errors.append(error_msg)
                if i in self.log_files:
                    self.log_files[i].write(f"\nERROR: {error_msg}\n")
                    self.log_files[i].flush()

        # Let them run briefly to detect usage errors
        time.sleep(2)

        # Check if we got usage errors
        if self._has_usage_errors():
            return False  # Signal that we need to retry

        # Continue running for the full runtime
        time.sleep(runtime - 2)

        # Cleanup
        self.stop_nodes()
        return True

    def _has_usage_errors(self):
        """Check if processes are outputting usage messages (incorrect arguments)"""
        for node_id, lines in self.outputs.items():
            for _, line in lines:
                line_lower = line.lower()
                # More comprehensive usage detection
                if ('usage:' in line_lower or 'error:' in line_lower) and \
                   ('python' in line_lower or 'lab' in line_lower or 'argument' in line_lower):
                    return True
        return False

    def get_attempted_commands(self):
        """Get the commands that were attempted for debugging"""
        commands = []
        for i, (days, su_id, month_day, month_day_year) in enumerate(NODE_CONFIGS):
            listen_port = BASE_LISTEN_PORT + i
            if self.arg_generator:
                args = self.arg_generator('localhost', 50000, listen_port, su_id, days, month_day, month_day_year)
            else:
                args = ['localhost', '50000', str(days), str(su_id)]
            cmd = f"python3 {self.lab_file} {' '.join(args)}"
            commands.append(cmd)
        return commands

    def _collect_output(self, process, node_id):
        """Collect stdout/stderr from a process and write to log file"""
        try:
            while True:
                line = process.stdout.readline()
                if not line and process.poll() is not None:
                    break
                if line:
                    stripped_line = line.strip()
                    timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
                    self.outputs[node_id].append(('output', stripped_line))

                    # Write to log file
                    if node_id in self.log_files:
                        self.log_files[node_id].write(f"[{timestamp}] {stripped_line}\n")
                        self.log_files[node_id].flush()

                    # Print real-time output in verbose mode
                    if self.verbose and stripped_line:
                        self._print_node_output(node_id, stripped_line)
        except Exception as e:
            error_msg = f"Error collecting output for node {node_id}: {str(e)}"
            if node_id in self.log_files:
                self.log_files[node_id].write(f"\nERROR: {error_msg}\n")
                self.log_files[node_id].flush()

    def _print_node_output(self, node_id, line):
        """Print formatted node output with highlighting for important events"""
        # Get node info
        days, su_id, month_day, month_day_year = NODE_CONFIGS[node_id]
        node_label = f"[Node{node_id}|{days}d|{su_id}]"

        # Color codes (ANSI)
        RESET = '\033[0m'
        GREEN = '\033[92m'
        YELLOW = '\033[93m'
        BLUE = '\033[94m'
        MAGENTA = '\033[95m'
        CYAN = '\033[96m'
        RED = '\033[91m'
        BOLD = '\033[1m'

        line_lower = line.lower()

        # Highlight important events
        if 'election' in line_lower and 'started' in line_lower:
            print(f"{BOLD}{YELLOW}{node_label} ELECTION: {line}{RESET}", flush=True)
        elif 'i_am_leader' in line_lower or 'become leader' in line_lower:
            print(f"{BOLD}{GREEN}{node_label} LEADER: {line}{RESET}", flush=True)
        elif 'new leader' in line_lower:
            print(f"{BOLD}{GREEN}{node_label} NEW LEADER: {line}{RESET}", flush=True)
        elif 'elect' in line_lower and 'response' in line_lower:
            print(f"{CYAN}{node_label} ELECT RESPONSE: {line}{RESET}", flush=True)
        elif 'elect' in line_lower:
            print(f"{BLUE}{node_label} ELECT: {line}{RESET}", flush=True)
        elif 'probe' in line_lower and 'failed' in line_lower:
            print(f"{RED}{node_label} PROBE FAILED: {line}{RESET}", flush=True)
        elif 'probe' in line_lower:
            print(f"{CYAN}{node_label} PROBE: {line}{RESET}", flush=True)
        elif 'fail' in line_lower and 'simulat' in line_lower:
            print(f"{RED}{node_label} FAILURE: {line}{RESET}", flush=True)
        elif 'recover' in line_lower:
            print(f"{GREEN}{node_label} RECOVER: {line}{RESET}", flush=True)
        elif 'join' in line_lower or 'howdy' in line_lower:
            print(f"{MAGENTA}{node_label} JOIN: {line}{RESET}", flush=True)
        elif 'listen' in line_lower or 'port' in line_lower:
            print(f"{MAGENTA}{node_label} LISTEN: {line}{RESET}", flush=True)
        elif 'error' in line_lower or 'exception' in line_lower:
            print(f"{RED}{node_label} ERROR: {line}{RESET}", flush=True)
        else:
            # Regular output
            print(f"{node_label} {line}", flush=True)



    def stop_nodes(self):
        """Stop all running node processes"""
        for process in self.processes:
            try:
                process.terminate()
                process.wait(timeout=2)
            except:
                try:
                    process.kill()
                except:
                    pass

        # Close all log files
        for node_id, log_file in self.log_files.items():
            try:
                log_file.write(f"\n{'='*60}\n")
                log_file.write(f"Node stopped at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                log_file.close()
            except:
                pass

    def get_summary(self):
        """Get a summary of the test run"""
        return {
            "student": self.student_name,
            "nodes_started": len(self.processes),
            "errors": self.errors,
            "log_files": [f"node{i}.log" for i in self.log_files.keys()],
            "timestamp": datetime.now().isoformat()
        }


class GCDServer:
    """Manages the GCD server process"""

    def __init__(self, gcd_script, port):
        self.gcd_script = gcd_script
        self.port = port
        self.process = None

    def start(self):
        """Start the GCD server"""
        # Check if port is already in use
        if is_port_in_use(self.port):
            print(f"WARNING: Port {self.port} is already in use!")
            response = input(f"Do you want to try to use the existing service on port {self.port}? (y/n): ").strip().lower()
            if response == 'y' or response == 'yes':
                print(f"Will attempt to use existing service on port {self.port}")
                return True
            else:
                raise Exception(f"Port {self.port} is already in use. Please choose a different port or stop the existing service.")

        try:
            self.process = subprocess.Popen(
                ["python3", self.gcd_script, str(self.port)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            time.sleep(1)  # Give it time to start

            if self.process.poll() is not None:
                raise Exception("GCD server failed to start")

            return True
        except Exception as e:
            print(f"Error starting GCD: {e}")
            return False

    def stop(self):
        """Stop the GCD server"""
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=2)
            except:
                try:
                    self.process.kill()
                except:
                    pass


def find_student_submissions(base_dir="."):
    """Find all student lab2.py submissions"""
    submissions = {}
    base_path = Path(base_dir)

    for student_dir in base_path.iterdir():
        if student_dir.is_dir() and not student_dir.name.startswith('.'):
            lab_file = student_dir / "lab2.py"
            # Also check for Lab2.py (capital L)
            if not lab_file.exists():
                lab_file = student_dir / "Lab2.py"

            if lab_file.exists():
                submissions[student_dir.name] = {
                    'lab_file': str(lab_file),
                    'student_dir': str(student_dir)
                }

    return submissions


def load_usage_patterns(folder_args_file="folder_args.md"):
    """Load student usage patterns from folder_args.md"""
    usage_patterns = {}

    if not os.path.exists(folder_args_file):
        return usage_patterns

    with open(folder_args_file, 'r') as f:
        content = f.read()

    # Parse student sections
    student_sections = re.split(r'Student: (\w+)', content)

    for i in range(1, len(student_sections), 2):
        student_name = student_sections[i]
        section_text = student_sections[i + 1]

        # Extract usage line
        usage_match = re.search(r'Usage:(.+?)(?:\n|$)', section_text, re.IGNORECASE)
        if usage_match:
            usage_patterns[student_name] = usage_match.group(1).strip()

    return usage_patterns


def prompt_for_argument_format(student_name, arg_generator, usage_text=None):
    """
    Prompt user to confirm or provide argument template before testing

    Returns: arg_generator function or None to skip
    """
    print(f"\n{'-'*60}")
    print(f"ARGUMENT FORMAT CONFIRMATION for {student_name}")
    print(f"{'-'*60}")

    # Show usage text if available
    if usage_text:
        print(f"\nDetected usage from folder_args.md:")
        print(f"  {usage_text}")

    # Generate sample command with current/auto-detected args
    sample_args = None
    if arg_generator:
        try:
            sample_args = arg_generator('localhost', 50000, 60000, 1234567, 100, '01-29', '01-29-2026')
            print(f"\nAuto-detected argument format:")
            print(f"  python3 lab2.py {' '.join(sample_args)}")
        except:
            print(f"\nNo auto-detected argument format available")
    else:
        print(f"\nNo auto-detected argument format available")
        print(f"Default would be: python3 lab2.py localhost 50000 100 1234567")

    print("\n" + "-"*60)
    print("Available template variables:")
    print("  {gcd_host}       - GCD server hostname")
    print("  {gcd_port}       - GCD server port")
    print("  {listen_port}    - Node's listening port")
    print("  {su_id}          - Student ID")
    print("  {days}           - Days to birthday")
    print("  {month_day}      - Birthday in MM-DD format")
    print("  {month_day_year} - Birthday in MM-DD-YYYY format")
    print("\nCommon templates:")
    print("  1. {gcd_host} {gcd_port} {listen_port} {su_id} {month_day}")
    print("  2. {gcd_host} {gcd_port} {su_id} {days}")
    print("  3. {su_id} {days} {gcd_host} {gcd_port}")
    print("  4. {days} {su_id} {gcd_host} {gcd_port}")
    print("  5. {gcd_host} {gcd_port} {days} {su_id}")
    print("  6. {gcd_host} {gcd_port} {su_id} {month_day_year}")
    print("\n" + "-"*60)

    while True:
        response = input("\nUse auto-detected format? (y/n/skip): ").strip().lower()

        if response == 'skip':
            return None

        if response == 'y' or response == 'yes':
            if arg_generator:
                return arg_generator
            else:
                # Use default
                return None

        if response == 'n' or response == 'no':
            # Ask for custom template
            template = input("\nEnter custom template: ").strip()

            if not template:
                print("ERROR: Template cannot be empty. Try again.")
                continue

            # Validate template has at least some variables
            if '{' not in template:
                print("ERROR: Template should contain variables like {gcd_host}, {gcd_port}, etc.")
                continue

            # Try to create generator
            try:
                arg_gen = ArgumentParser.parse_template(template)
                # Test it
                test_args = arg_gen('localhost', 50000, 60000, 1234567, 100, '01-29', '01-29-2026')
                print(f"\nTemplate accepted. Test command:")
                print(f"  python3 lab2.py {' '.join(test_args)}")

                confirm = input("\nIs this correct? (y/n): ").strip().lower()
                if confirm == 'y' or confirm == 'yes':
                    return arg_gen
                else:
                    print("\nLet's try again...")
                    continue

            except Exception as e:
                print(f"ERROR: Error with template: {e}")
                continue
        else:
            print("ERROR: Please enter 'y' for yes, 'n' for no, or 'skip' to skip this student.")


def prompt_for_template_on_error(student_name, usage_output, attempted_commands):
    """
    Prompt user to provide argument template when usage errors are detected

    Returns: arg_generator function or None to skip
    """
    print(f"\n{'!'*60}")
    print(f"ARGUMENT FORMAT ERROR for {student_name}")
    print(f"{'!'*60}")
    print("\nThe provided argument format appears to be incorrect.")
    print("\nUsage message from student's code:")
    for line in usage_output:
        print(f"  {line}")

    print("\nAttempted command (Node 0 example):")
    if attempted_commands:
        print(f"  {attempted_commands[0]}")

    print("\n" + "-"*60)
    print("Please provide the correct argument template:")
    print("\nAvailable variables:")
    print("  {gcd_host}       - GCD server hostname")
    print("  {gcd_port}       - GCD server port")
    print("  {listen_port}    - Node's listening port")
    print("  {su_id}          - Student ID")
    print("  {days}           - Days to birthday")
    print("  {month_day}      - Birthday in MM-DD format")
    print("  {month_day_year} - Birthday in MM-DD-YYYY format")
    print("\nCommon templates:")
    print("  1. {gcd_host} {gcd_port} {listen_port} {su_id} {month_day}")
    print("  2. {gcd_host} {gcd_port} {su_id} {days}")
    print("  3. {su_id} {days} {gcd_host} {gcd_port}")
    print("  4. {days} {su_id} {gcd_host} {gcd_port}")
    print("  5. {gcd_host} {gcd_port} {su_id} {month_day_year}")
    print("\n" + "-"*60)

    while True:
        template = input("\nEnter template (or 'skip' to skip this student): ").strip()

        if template.lower() == 'skip':
            return None

        if not template:
            print("ERROR: Template cannot be empty. Try again.")
            continue

        # Validate template has at least some variables
        if '{' not in template:
            print("ERROR: Template should contain variables like {gcd_host}, {gcd_port}, etc.")
            continue

        # Try to create generator
        try:
            arg_gen = ArgumentParser.parse_template(template)
            # Test it
            test_args = arg_gen('localhost', 50000, 60000, 1234567, 100, '01-29', '01-29-2026')
            print(f"\nTemplate accepted. Test command:")
            print(f"  python3 lab2.py {' '.join(test_args)}")

            confirm = input("\nIs this correct? (y/n): ").strip().lower()
            if confirm == 'y':
                return arg_gen
            else:
                print("\nLet's try again...")
                continue

        except Exception as e:
            print(f"ERROR: Error with template: {e}")
            continue


def main():
    parser = argparse.ArgumentParser(description='Test Bully Algorithm submissions')
    parser.add_argument('--students', help='Comma-separated list of students to test')
    parser.add_argument('--timeout', type=int, default=RUNTIME_SECONDS,
                       help=f'Runtime per student in seconds (default: {RUNTIME_SECONDS})')
    parser.add_argument('--gcd-port', type=int, default=GCD_PORT,
                       help=f'GCD port (default: {GCD_PORT})')
    parser.add_argument('--output', default='test_results.json',
                       help='Output JSON file (default: test_results.json)')
    parser.add_argument('--base-dir', default='.',
                       help='Base directory containing student folders (default: current directory)')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Show real-time output from nodes with color-coded events')

    args = parser.parse_args()

    # Find GCD script
    gcd_script = "gcd2.py"
    if not os.path.exists(gcd_script):
        print(f"Error: {gcd_script} not found!")
        return 1

    # Load usage patterns
    usage_patterns = load_usage_patterns()

    # Find student submissions
    submissions = find_student_submissions(args.base_dir)

    if not submissions:
        print("No student submissions found!")
        return 1

    # Filter students if specified
    if args.students:
        student_list = [s.strip() for s in args.students.split(',')]
        submissions = {k: v for k, v in submissions.items() if k in student_list}

    print(f"Found {len(submissions)} student(s) to test")
    print(f"Students: {', '.join(submissions.keys())}")

    # Results container
    results = {}

    print(f"\nTesting students sequentially")
    print(f"{'='*60}\n")

    # Start GCD server
    print(f"Starting GCD server on port {args.gcd_port}...")
    gcd = GCDServer(gcd_script, args.gcd_port)

    if not gcd.start():
        print("Failed to start GCD server!")
        return 1

    print("GCD server started successfully")

    try:
        # Test each student
        for student_name, student_data in submissions.items():
            print(f"\n{'='*60}")
            print(f"Testing: {student_name}")
            print(f"{'='*60}")

            lab_file = student_data['lab_file']
            student_dir = student_data['student_dir']

            # Get argument generator for this student
            usage_text = usage_patterns.get(student_name, "")
            arg_generator = ArgumentParser.parse_usage_line(usage_text)

            # Always prompt user to confirm/change argument format
            confirmed_generator = prompt_for_argument_format(student_name, arg_generator, usage_text)

            if confirmed_generator is None and arg_generator is None:
                # User chose to skip or no generator available
                skip_response = input("\nNo argument format specified. Skip this student? (y/n): ").strip().lower()
                if skip_response == 'y' or skip_response == 'yes':
                    print(f"\nSkipping {student_name}")
                    results[student_name] = {
                        "status": "skipped",
                        "reason": "No argument format",
                        "timestamp": datetime.now().isoformat()
                    }
                    # Reset GCD
                    gcd.stop()
                    time.sleep(1)
                    gcd.start()
                    continue

            # Use confirmed generator (or keep the auto-detected one if user said yes)
            if confirmed_generator is not None:
                arg_generator = confirmed_generator

            # Try testing, with retry if argument format is wrong
            success = False
            max_retries = 3
            for attempt in range(max_retries):
                # Create tester
                tester = StudentTester(student_name, lab_file, arg_generator,
                                      student_dir, verbose=args.verbose)

                # Run and collect output
                if args.verbose:
                    print(f"\nRunning {NUM_NODES} nodes for {args.timeout} seconds...")
                    print(f"{'-'*60}")
                    print("Real-time node output (color-coded):")
                    print(f"{'-'*60}")
                else:
                    print(f"\nRunning {NUM_NODES} nodes for {args.timeout} seconds...")

                run_success = tester.run_nodes("localhost", args.gcd_port, args.timeout)

                if run_success:
                    # No usage errors, proceed
                    success = True
                    break
                else:
                    # Usage errors detected - prompt for manual input
                    tester.stop_nodes()  # Clean up failed processes

                    # Extract usage messages
                    usage_lines = []
                    for node_id, lines in tester.outputs.items():
                        for _, line in lines:
                            if 'usage:' in line.lower() or 'error:' in line.lower():
                                usage_lines.append(line)
                        if usage_lines:
                            break  # Just need one example

                    # Get attempted commands for display
                    attempted_cmds = tester.get_attempted_commands()

                    # Prompt user for correct template
                    new_generator = prompt_for_template_on_error(student_name, usage_lines, attempted_cmds)

                    if new_generator is None:
                        # User chose to skip this student
                        print(f"\nSkipping {student_name}")
                        results[student_name] = {
                            "status": "skipped",
                            "reason": "Incorrect argument format",
                            "timestamp": datetime.now().isoformat()
                        }
                        break

                    # Update arg_generator and retry
                    arg_generator = new_generator
                    print(f"\nRetrying with new argument format...")

                    # Reset GCD
                    gcd.stop()
                    time.sleep(1)
                    gcd.start()

            if success:
                print("\nTest completed successfully")
                summary = tester.get_summary()
                results[student_name] = summary

                # Print summary
                print(f"\nResults for {student_name}:")
                print(f"  Nodes started: {summary['nodes_started']}")
                print(f"  Log files saved: {', '.join(summary['log_files'])}")
                if summary['errors']:
                    print("  Errors:")
                    for error in summary['errors']:
                        print(f"    ERROR: {error}")

            # Reset GCD between students
            gcd.stop()
            time.sleep(1)
            gcd.start()

    finally:
        # Cleanup GCD
        print("\nStopping GCD server...")
        gcd.stop()

    # Save results to JSON
    output_file = args.output
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)

    print(f"\n{'='*60}")
    print(f"Testing complete! Results saved to {output_file}")
    print(f"{'='*60}")

    # Print summary table
    print("\nSummary:")
    print(f"{'Student':<20} {'Status':<15} {'Log Files'}")
    print("-" * 60)
    for student, result in results.items():
        status = result.get('status', 'completed')
        log_files = ', '.join(result.get('log_files', []))
        print(f"{student:<20} {status:<15} {log_files}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
