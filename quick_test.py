#!/usr/bin/env python3
"""
Quick Test Script for Individual Student Submissions

This script allows you to quickly test a single student's Lab2 implementation
interactively to see real-time output and behavior.

Usage:
    python3 quick_test.py student_name [num_nodes] [runtime]

Example:
    python3 quick_test.py ychoi4 3 20
"""

import sys
import subprocess
import time
import os
from pathlib import Path

GCD_PORT = 50001  # Different from grading script to avoid conflicts
BASE_PORT = 61000

NODE_CONFIGS = [
    (100, 1234567, "01-29"),
    (50, 2345678, "12-11"),
    (200, 3456789, "07-09"),
    (150, 4567890, "03-20"),
]


def parse_usage_for_student(student_name):
    """Load usage pattern from folder_args.md"""
    if not os.path.exists("folder_args.md"):
        return None

    with open("folder_args.md", 'r') as f:
        content = f.read()

    # Find student section
    import re
    pattern = f"Student: {student_name}.*?Usage:(.+?)(?:\n|$)"
    match = re.search(pattern, content, re.IGNORECASE | re.DOTALL)

    if match:
        return match.group(1).strip()
    return None


def generate_args(usage_text, gcd_host, gcd_port, listen_port, su_id, days, month_day):
    """Generate arguments based on usage pattern"""
    if not usage_text:
        return [gcd_host, str(gcd_port), str(days), str(su_id)]

    usage_lower = usage_text.lower()

    # Pattern matching
    if 'listen' in usage_lower and 'port' in usage_lower and \
       usage_lower.index('listen') < usage_lower.index('su'):
        # GCD_HOST GCD_PORT LISTEN_PORT SU_ID B-DAY
        return [gcd_host, str(gcd_port), str(listen_port), str(su_id), month_day]

    elif 'su' in usage_lower and usage_lower.index('su') < usage_lower.index('day'):
        # SU_ID days GCD_HOST GCD_PORT
        return [str(su_id), str(days), gcd_host, str(gcd_port)]

    elif 'day' in usage_lower and usage_lower.index('day') < usage_lower.index('su'):
        # days SU_ID GCD_HOST GCD_PORT
        return [str(days), str(su_id), gcd_host, str(gcd_port)]

    elif 'bday' in usage_lower and usage_lower.index('bday') < usage_lower.index('host'):
        # BDAY SUID HOST PORT
        return [str(days), str(su_id), gcd_host, str(gcd_port)]

    elif 'month' in usage_lower and 'day' in usage_lower:
        # SU_ID month day [gcd_host] [gcd_port]
        return [str(su_id)] + month_day.split('-') + [gcd_host, str(gcd_port)]

    else:
        # Default: GCD_HOST GCD_PORT days SU_ID
        return [gcd_host, str(gcd_port), str(days), str(su_id)]


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 quick_test.py student_name [num_nodes] [runtime]")
        print("\nExample: python3 quick_test.py ychoi4 3 20")
        return 1

    student_name = sys.argv[1]
    num_nodes = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    runtime = int(sys.argv[3]) if len(sys.argv) > 3 else 20

    # Find student's lab2.py
    lab_file = Path(student_name) / "lab2.py"
    if not lab_file.exists():
        lab_file = Path(student_name) / "Lab2.py"

    if not lab_file.exists():
        print(f"Error: Could not find lab2.py for student '{student_name}'")
        print(f"Expected location: {student_name}/lab2.py")
        return 1

    # Check for gcd2.py
    if not os.path.exists("gcd2.py"):
        print("Error: gcd2.py not found in current directory!")
        return 1

    # Get usage pattern
    usage_text = parse_usage_for_student(student_name)
    if usage_text:
        print(f"Detected usage: {usage_text}")
    else:
        print(f"No usage pattern found for {student_name}, using default")

    print(f"\n{'='*60}")
    print(f"Quick Test: {student_name}")
    print(f"{'='*60}")
    print(f"Running {num_nodes} nodes for {runtime} seconds")
    print(f"GCD Port: {GCD_PORT}")
    print(f"Base Listen Port: {BASE_PORT}")
    print(f"{'='*60}\n")

    # Start GCD
    print("Starting GCD server...")
    gcd_process = subprocess.Popen(
        ["python3", "gcd2.py", str(GCD_PORT)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    time.sleep(1)

    if gcd_process.poll() is not None:
        print("Error: GCD server failed to start!")
        return 1

    print("GCD server started\n")

    processes = []

    try:
        # Start nodes
        for i in range(num_nodes):
            days, su_id, month_day = NODE_CONFIGS[i]
            listen_port = BASE_PORT + i

            args = generate_args(usage_text, "localhost", GCD_PORT, listen_port,
                               su_id, days, month_day)

            cmd = ["python3", str(lab_file)] + args

            print(f"Starting Node {i} (priority: {days} days, SU_ID: {su_id})")
            print(f"  Command: {' '.join(cmd)}")

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env={**os.environ, 'PYTHONUNBUFFERED': '1'}
            )

            processes.append((i, process))
            time.sleep(0.5)

        print(f"\n{'='*60}")
        print(f"All {num_nodes} nodes started. Monitoring output...")
        print(f"{'='*60}\n")

        # Monitor output from all processes
        start_time = time.time()
        while time.time() - start_time < runtime:
            for node_id, process in processes:
                if process.poll() is not None:
                    # Process died
                    continue

                try:
                    line = process.stdout.readline()
                    if line:
                        print(f"[Node {node_id}] {line.rstrip()}")
                except:
                    pass

            time.sleep(0.1)

        print(f"\n{'='*60}")
        print(f"Test complete after {runtime} seconds")
        print(f"{'='*60}\n")

    except KeyboardInterrupt:
        print("\n\nInterrupted by user")

    finally:
        # Cleanup
        print("Stopping all processes...")
        for node_id, process in processes:
            try:
                process.terminate()
                process.wait(timeout=2)
            except:
                try:
                    process.kill()
                except:
                    pass

        try:
            gcd_process.terminate()
            gcd_process.wait(timeout=2)
        except:
            try:
                gcd_process.kill()
            except:
                pass

        print("All processes stopped")

    return 0


if __name__ == "__main__":
    sys.exit(main())
