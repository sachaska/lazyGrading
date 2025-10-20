#!/usr/bin/env python3
"""
Grading Script for Lab2: Bully Algorithm
Distributed Systems Class

This script:
1. Starts a GCD server
2. Launches multiple instances of each student's submission
3. Monitors their behavior and communication
4. Grades based on Bully Algorithm requirements
5. Generates a JSON grading log

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
from pathlib import Path
from collections import defaultdict
from datetime import datetime

# Configuration
GCD_PORT = 50000
BASE_LISTEN_PORT = 60000
RUNTIME_SECONDS = 30
NUM_NODES = 4  # Number of nodes to simulate per student

# Grading criteria points
POINTS = {
    "process_startup": 5,
    "gcd_join": 10,
    "listens_properly": 5,
    "election_participation": 20,
    "leader_consensus": 15,
    "message_handling": 5,
    "probe_handling": 5,  # Extra credit
    "failure_simulation": 5,  # Extra credit
}

# Test node configurations (days_to_birthday, su_id)
# These create different priorities for the Bully algorithm
NODE_CONFIGS = [
    (100, 1234567, "01-29"),  # Lowest priority
    (50, 2345678, "12-11"),   # Medium priority
    (200, 3456789, "07-09"),  # Higher priority
    (150, 4567890, "03-20"),  # Highest priority (becomes leader)
]


class ArgumentParser:
    """Parse different student argument formats"""

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
            # Pattern: GCD_HOST GCD_PORT LISTEN_PORT SU_ID B-DAY
            (r'gcd.*host.*gcd.*port.*listen.*port.*su.*id.*b.*day|b.*day',
             lambda gcd_host, gcd_port, listen_port, su_id, bday, month_day:
                [gcd_host, str(gcd_port), str(listen_port), str(su_id), month_day]),

            # Pattern: SU_ID days_to_bday GCD_HOST GCD_PORT
            (r'su.*id.*day.*gcd.*host.*gcd.*port',
             lambda gcd_host, gcd_port, listen_port, su_id, bday, month_day:
                [str(su_id), str(bday), gcd_host, str(gcd_port)]),

            # Pattern: days_to_bday SU_ID GCD_HOST GCD_PORT
            (r'day.*su.*id.*host.*port',
             lambda gcd_host, gcd_port, listen_port, su_id, bday, month_day:
                [str(bday), str(su_id), gcd_host, str(gcd_port)]),

            # Pattern: GCD_HOST GCD_PORT SU_ID days_to_bday
            (r'gcd.*host.*gcd.*port.*su.*id.*day|gcd.*host.*gcd.*port.*student.*id.*birth',
             lambda gcd_host, gcd_port, listen_port, su_id, bday, month_day:
                [gcd_host, str(gcd_port), str(su_id), str(bday)]),

            # Pattern: GCD_HOST GCD_PORT days_to_bday SU_ID
            (r'gcd.*host.*gcd.*port.*day.*su.*id|gcd.*host.*gcd.*port.*n.*day.*student',
             lambda gcd_host, gcd_port, listen_port, su_id, bday, month_day:
                [gcd_host, str(gcd_port), str(bday), str(su_id)]),

            # Pattern: BDAY SUID HOST PORT
            (r'bday.*suid.*host.*port',
             lambda gcd_host, gcd_port, listen_port, su_id, bday, month_day:
                [str(bday), str(su_id), gcd_host, str(gcd_port)]),

            # Pattern: GCD_HOST GCD_PORT (minimal args)
            (r'gcd.*host.*gcd.*port$',
             lambda gcd_host, gcd_port, listen_port, su_id, bday, month_day:
                [gcd_host, str(gcd_port)]),

            # Pattern: SU_ID month day [gcd_host] [gcd_port]
            (r'su.*id.*month.*day',
             lambda gcd_host, gcd_port, listen_port, su_id, bday, month_day:
                [str(su_id)] + month_day.split('-') + [gcd_host, str(gcd_port)]),

            # Pattern: GCD_HOST GCD_PORT SU_ID MOM_BDAY_MM-DD
            (r'gcd.*host.*gcd.*port.*su.*id.*mom.*bday.*mm.*dd',
             lambda gcd_host, gcd_port, listen_port, su_id, bday, month_day:
                [gcd_host, str(gcd_port), str(su_id), month_day]),

            # Pattern: GCD_HOST GCD_PORT BIRTH_MONTH BIRTH_DAY SU_ID
            (r'gcd.*host.*gcd.*port.*birth.*month.*birth.*day.*su.*id',
             lambda gcd_host, gcd_port, listen_port, su_id, bday, month_day:
                [gcd_host, str(gcd_port)] + month_day.split('-') + [str(su_id)]),
        ]

        for pattern, arg_func in patterns:
            if re.search(pattern, usage_lower):
                return arg_func

        # Default fallback: assume GCD_HOST GCD_PORT days SU_ID
        return lambda gcd_host, gcd_port, listen_port, su_id, bday, month_day: \
            [gcd_host, str(gcd_port), str(bday), str(su_id)]


class StudentGrader:
    """Grades a single student's submission"""

    def __init__(self, student_name, lab_file, arg_generator, verbose=False):
        self.student_name = student_name
        self.lab_file = lab_file
        self.arg_generator = arg_generator
        self.verbose = verbose
        self.processes = []
        self.outputs = defaultdict(list)
        self.scores = {key: 0 for key in POINTS.keys()}
        self.comments = []
        self.errors = []

    def run_nodes(self, gcd_host, gcd_port, runtime):
        """Launch multiple node instances for this student"""
        for i, (days, su_id, month_day) in enumerate(NODE_CONFIGS):
            listen_port = BASE_LISTEN_PORT + i

            try:
                if self.arg_generator:
                    args = self.arg_generator(gcd_host, gcd_port, listen_port,
                                             su_id, days, month_day)
                else:
                    # Default argument order
                    args = [gcd_host, str(gcd_port), str(days), str(su_id)]

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
                self.errors.append(f"Failed to start node {i}: {str(e)}")

        # Let them run
        time.sleep(runtime)

        # Cleanup
        self.stop_nodes()

    def _collect_output(self, process, node_id):
        """Collect stdout/stderr from a process"""
        try:
            while True:
                line = process.stdout.readline()
                if not line and process.poll() is not None:
                    break
                if line:
                    stripped_line = line.strip()
                    self.outputs[node_id].append(('output', stripped_line))

                    # Print real-time output in verbose mode
                    if self.verbose and stripped_line:
                        self._print_node_output(node_id, stripped_line)
        except Exception as e:
            pass

    def _print_node_output(self, node_id, line):
        """Print formatted node output with highlighting for important events"""
        # Get node info
        days, su_id, month_day = NODE_CONFIGS[node_id]
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
            print(f"{BOLD}{YELLOW}{node_label} 🗳️  {line}{RESET}", flush=True)
        elif 'i_am_leader' in line_lower or 'become leader' in line_lower:
            print(f"{BOLD}{GREEN}{node_label} 👑 {line}{RESET}", flush=True)
        elif 'new leader' in line_lower:
            print(f"{BOLD}{GREEN}{node_label} ✓  {line}{RESET}", flush=True)
        elif 'elect' in line_lower and 'response' in line_lower:
            print(f"{CYAN}{node_label} 📨 {line}{RESET}", flush=True)
        elif 'elect' in line_lower:
            print(f"{BLUE}{node_label} 🗳️  {line}{RESET}", flush=True)
        elif 'probe' in line_lower and 'failed' in line_lower:
            print(f"{RED}{node_label} ❌ {line}{RESET}", flush=True)
        elif 'probe' in line_lower:
            print(f"{CYAN}{node_label} 🔍 {line}{RESET}", flush=True)
        elif 'fail' in line_lower and 'simulat' in line_lower:
            print(f"{RED}{node_label} 💀 {line}{RESET}", flush=True)
        elif 'recover' in line_lower:
            print(f"{GREEN}{node_label} 💚 {line}{RESET}", flush=True)
        elif 'join' in line_lower or 'howdy' in line_lower:
            print(f"{MAGENTA}{node_label} 🤝 {line}{RESET}", flush=True)
        elif 'listen' in line_lower or 'port' in line_lower:
            print(f"{MAGENTA}{node_label} 👂 {line}{RESET}", flush=True)
        elif 'error' in line_lower or 'exception' in line_lower:
            print(f"{RED}{node_label} ⚠️  {line}{RESET}", flush=True)
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

    def analyze_and_grade(self):
        """Analyze collected output and assign grades"""

        # Combine all output
        all_output = []
        for node_id, lines in self.outputs.items():
            all_output.extend([line[1] for line in lines])

        output_text = '\n'.join(all_output).lower()

        # Check process startup
        if len(self.processes) > 0 and not self.errors:
            self.scores["process_startup"] = POINTS["process_startup"]
            self.comments.append("✓ Process started")
        else:
            self.errors.append("Process failed to start")

        # Check GCD join
        if re.search(r'join|howdy|gcd', output_text):
            self.scores["gcd_join"] = POINTS["gcd_join"]
            self.comments.append("✓ GCD join detected")
        else:
            self.errors.append("No GCD join detected")

        # Check listening
        port_match = re.search(r'(port|listen).*?(\d{5})', output_text)
        if port_match or re.search(r'listen|server', output_text):
            self.scores["listens_properly"] = POINTS["listens_properly"]
            if port_match:
                self.comments.append(f"✓ Port {port_match.group(2)}")
            else:
                self.comments.append("✓ Listening server started")

        # Check election participation
        elect_count = len(re.findall(r'elect', output_text))
        if elect_count >= 2:
            self.scores["election_participation"] = POINTS["election_participation"]
            self.comments.append(f"✓ ELECT messages ({elect_count} occurrences)")
        elif elect_count == 1:
            self.scores["election_participation"] = POINTS["election_participation"] // 2
            self.comments.append("⚠ Limited election participation")
        else:
            self.errors.append("No ELECT messages detected")

        # Check leader consensus
        leader_count = len(re.findall(r'leader|i_am_leader', output_text))
        if leader_count >= 1:
            self.scores["leader_consensus"] = POINTS["leader_consensus"]
            self.comments.append(f"✓ Leader consensus ({leader_count} occurrences)")
        else:
            self.errors.append("No leader consensus detected")

        # Check message handling (GOT_IT responses)
        if re.search(r'got_it|response|recv', output_text):
            self.scores["message_handling"] = POINTS["message_handling"]
            self.comments.append("✓ Message handling detected")

        # Extra Credit: PROBE handling
        probe_count = len(re.findall(r'probe', output_text))
        if probe_count >= 2:
            self.scores["probe_handling"] = POINTS["probe_handling"]
            self.comments.append(f"✓ EC: PROBE handling ({probe_count} occurrences)")

        # Extra Credit: Failure simulation
        failure_count = len(re.findall(r'fail|recover', output_text))
        if failure_count >= 2:
            self.scores["failure_simulation"] = POINTS["failure_simulation"]
            self.comments.append(f"✓ EC: Failure simulation ({failure_count} occurrences)")

        return {
            "scores": self.scores,
            "comments": self.comments,
            "errors": self.errors,
            "total": sum(self.scores.values())
        }


class GCDServer:
    """Manages the GCD server process"""

    def __init__(self, gcd_script, port):
        self.gcd_script = gcd_script
        self.port = port
        self.process = None

    def start(self):
        """Start the GCD server"""
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
                submissions[student_dir.name] = str(lab_file)

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


def main():
    parser = argparse.ArgumentParser(description='Grade Bully Algorithm submissions')
    parser.add_argument('--students', help='Comma-separated list of students to grade')
    parser.add_argument('--timeout', type=int, default=RUNTIME_SECONDS,
                       help=f'Runtime per student in seconds (default: {RUNTIME_SECONDS})')
    parser.add_argument('--gcd-port', type=int, default=GCD_PORT,
                       help=f'GCD port (default: {GCD_PORT})')
    parser.add_argument('--output', default='grading_results.json',
                       help='Output JSON file (default: grading_results.json)')
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

    print(f"Found {len(submissions)} student(s) to grade")
    print(f"Students: {', '.join(submissions.keys())}")

    # Results container
    results = {}

    # Start GCD server
    print(f"\nStarting GCD server on port {args.gcd_port}...")
    gcd = GCDServer(gcd_script, args.gcd_port)

    if not gcd.start():
        print("Failed to start GCD server!")
        return 1

    print("GCD server started successfully")

    try:
        # Grade each student
        for student_name, lab_file in submissions.items():
            print(f"\n{'='*60}")
            print(f"Grading: {student_name}")
            print(f"{'='*60}")

            # Get argument generator for this student
            usage_text = usage_patterns.get(student_name, "")
            arg_generator = ArgumentParser.parse_usage_line(usage_text)

            # Create grader
            grader = StudentGrader(student_name, lab_file, arg_generator, verbose=args.verbose)

            # Run and grade
            if args.verbose:
                print(f"Running {NUM_NODES} nodes for {args.timeout} seconds...")
                print(f"{'─'*60}")
                print("Real-time node output (color-coded):")
                print(f"{'─'*60}")
            else:
                print(f"Running {NUM_NODES} nodes for {args.timeout} seconds...")
            grader.run_nodes("localhost", args.gcd_port, args.timeout)

            print("Analyzing output...")
            result = grader.analyze_and_grade()
            results[student_name] = result

            # Print summary
            print(f"\nResults for {student_name}:")
            print(f"  Total Score: {result['total']}/{sum(POINTS.values())}")
            if result['comments']:
                print("  Comments:")
                for comment in result['comments']:
                    print(f"    {comment}")
            if result['errors']:
                print("  Errors:")
                for error in result['errors']:
                    print(f"    ❌ {error}")

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
    print(f"Grading complete! Results saved to {output_file}")
    print(f"{'='*60}")

    # Print summary table
    print("\nSummary:")
    print(f"{'Student':<20} {'Total':<10} {'Status'}")
    print("-" * 50)
    for student, result in results.items():
        total = result['total']
        max_score = sum(POINTS.values())
        status = "✓ PASS" if total >= 50 else "✗ FAIL"
        print(f"{student:<20} {total}/{max_score:<8} {status}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
