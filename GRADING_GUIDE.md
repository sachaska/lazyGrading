# Bully Algorithm Grading Script

Automated grading system for Lab2: Bully Algorithm implementation in Distributed Systems class.

## Overview

This grading script (`grade_bully.py`) automatically:
- Starts a Group Coordinator Daemon (GCD) server
- Launches multiple instances of each student's submission to simulate a distributed system
- Monitors process behavior and communication patterns
- Scores submissions based on Bully Algorithm requirements
- Generates detailed JSON grading logs

## Prerequisites

- Python 3.6+
- All student submissions in proper folder structure
- `gcd2.py` (Group Coordinator Daemon) in the same directory

## Folder Structure

```
lazyGrading/
├── gcd2.py                    # Group Coordinator Daemon
├── grade_bully.py             # Main grading script
├── folder_args.md             # Student command-line argument patterns
├── lab2_instruction.md        # Lab requirements
├── grade_terms.md             # Grading criteria
├── student1/
│   └── lab2.py               # Student submission
├── student2/
│   └── lab2.py
└── ...
```

## Usage

### Basic Usage

Grade all students in the current directory:
```bash
python3 grade_bully.py
```

### Grade Specific Students

Grade only selected students:
```bash
python3 grade_bully.py --students ychoi4,tbanh,ncrouch
```

### Custom Options

```bash
python3 grade_bully.py \
  --base-dir ./submissions \
  --students ychoi4 \
  --timeout 30 \
  --gcd-port 50000 \
  --output results.json
```

### Verbose Mode (Debug Mode)

Watch real-time output from all nodes with color-coded events:
```bash
python3 grade_bully.py --students ychoi4 --verbose --timeout 15
```

This shows:
- 🗳️ **Yellow**: Elections starting
- 👑 **Green**: Leader elected
- 🔍 **Cyan**: PROBE messages
- 💀 **Red**: Node failures
- 💚 **Green**: Node recovery
- 🤝 **Magenta**: GCD join
- 📨 **Cyan**: Election responses
- Each line prefixed with `[NodeID|days|SU_ID]`

### Manual Argument Input

If the script detects incorrect arguments (usage messages from student code), it will automatically prompt you to provide the correct argument template:

```
⚠️  ARGUMENT FORMAT ERROR for student_name
The auto-detected argument format appears to be incorrect.

Usage message from student's code:
  Usage: python3 lab1.py GCD_HOST GCD_PORT LISTEN_PORT SU_ID B-DAY(MM-DD)

Attempted command (Node 0 example):
  python3 ychoi4/lab2.py localhost 50000 100 1234567

Please provide the correct argument template:

Available variables:
  {gcd_host}    - GCD server hostname
  {gcd_port}    - GCD server port
  {listen_port} - Node's listening port
  {su_id}       - Student ID
  {days}        - Days to birthday
  {month_day}   - Birthday in MM-DD format

Common templates:
  1. {gcd_host} {gcd_port} {listen_port} {su_id} {month_day}
  2. {gcd_host} {gcd_port} {su_id} {days}
  3. {su_id} {days} {gcd_host} {gcd_port}
  4. {days} {su_id} {gcd_host} {gcd_port}

Enter template (or 'skip' to skip this student): {gcd_host} {gcd_port} {listen_port} {su_id} {month_day}

✓ Template accepted. Test command:
  python3 lab2.py localhost 50000 60000 1234567 100 01-29

Is this correct? (y/n): y

🔄 Retrying with new argument format...
```

You can:
- Enter a custom template using the variables shown
- Type `skip` to skip grading this student
- The script will retry up to 3 times if needed

### Command-Line Options

| Option | Default | Description |
|--------|---------|-------------|
| `--students` | all | Comma-separated list of student names to grade |
| `--timeout` | 30 | Runtime per student in seconds |
| `--gcd-port` | 50000 | Port for GCD server |
| `--output` | `grading_results.json` | Output JSON file path |
| `--base-dir` | `.` | Base directory containing student folders |
| `--verbose`, `-v` | off | Show real-time output with color-coded events |

## Grading Criteria

The script evaluates submissions based on the following criteria:

| Category | Points | Description |
|----------|--------|-------------|
| **process_startup** | 5 | Process starts without errors |
| **gcd_join** | 10 | Successfully joins GCD with HOWDY message |
| **listens_properly** | 5 | Starts listening server on correct port |
| **election_participation** | 20 | Sends ELECT messages to higher processes |
| **leader_consensus** | 15 | Reaches consensus and announces leader |
| **message_handling** | 5 | Handles messages (GOT_IT responses) |
| **probe_handling** | 5 | Extra Credit: PROBE message implementation |
| **failure_simulation** | 5 | Extra Credit: Simulates failures and recovery |
| **Total** | **70** | Maximum possible score |

## How It Works

### 1. Node Simulation

For each student, the script launches 4 nodes with different priorities:
- Node 0: (100 days, SU_ID: 1234567) - Lowest priority
- Node 1: (50 days, SU_ID: 2345678) - Medium priority
- Node 2: (200 days, SU_ID: 3456789) - Higher priority
- Node 3: (150 days, SU_ID: 4567890) - Highest priority

### 2. Argument Pattern Detection

The script automatically detects each student's command-line argument format from `folder_args.md` and generates appropriate arguments. Supports patterns like:

- `GCD_HOST GCD_PORT LISTEN_PORT SU_ID B-DAY`
- `SU_ID days_to_bday GCD_HOST GCD_PORT`
- `GCD_HOST GCD_PORT days_to_bday SU_ID`
- Many more variations...

### 3. Output Analysis

The script monitors output for key patterns:
- **GCD Join**: Keywords like "join", "howdy", "gcd"
- **Elections**: "ELECT" messages
- **Leader**: "I_AM_LEADER" announcements
- **Probes**: "PROBE" messages (extra credit)
- **Failures**: "fail", "recover" keywords (extra credit)

### 4. Scoring

Each criterion is scored based on detected behaviors:
- Full points: Behavior detected and functioning correctly
- Partial points: Limited or incomplete implementation
- Zero points: Behavior not detected

## Output Format

### JSON Structure

```json
{
  "student_name": {
    "scores": {
      "process_startup": 5,
      "gcd_join": 10,
      "listens_properly": 5,
      "election_participation": 20,
      "leader_consensus": 15,
      "message_handling": 5,
      "probe_handling": 5,
      "failure_simulation": 0
    },
    "comments": [
      "✓ Process started",
      "✓ GCD join detected",
      "✓ Port 60000",
      "✓ ELECT messages (67 occurrences)",
      "✓ Leader consensus (47 occurrences)",
      "✓ Message handling detected",
      "✓ EC: PROBE handling (7 occurrences)"
    ],
    "errors": [],
    "total": 65
  }
}
```

### Console Output

The script provides real-time feedback:

```
============================================================
Grading: ychoi4
============================================================
Running 4 nodes for 30 seconds...
Analyzing output...

Results for ychoi4:
  Total Score: 70/70
  Comments:
    ✓ Process started
    ✓ GCD join detected
    ✓ Port 60000
    ✓ ELECT messages (67 occurrences)
    ...
```

## Troubleshooting

### Common Issues

**GCD Server Won't Start**
- Ensure port 50000 (or custom port) is available
- Check that `gcd2.py` is in the same directory
- Try a different port with `--gcd-port`

**Student Submission Not Found**
- Check folder structure matches: `student_name/lab2.py`
- Ensure student folder name matches exactly (case-sensitive)
- Some students may use `Lab2.py` (capital L)

**Process Timeout**
- Increase runtime with `--timeout 60` for slower systems
- Some implementations with frequent failures may need more time

**Incorrect Argument Format**
- Update `folder_args.md` with correct usage pattern
- The script uses pattern matching to detect argument order
- Add custom patterns in `ArgumentParser.parse_usage_line()` if needed

### Debug Mode

To see detailed output for a single student:
```bash
python3 grade_bully.py --students ychoi4 --timeout 10
```

## Testing

Test with the example submission:
```bash
# Create test structure
mkdir -p test_submissions/ychoi4
cp lab2.py test_submissions/ychoi4/

# Run grading
python3 grade_bully.py --base-dir test_submissions --timeout 15
```

## Customization

### Modify Node Configurations

Edit `NODE_CONFIGS` in `grade_bully.py`:
```python
NODE_CONFIGS = [
    (days_to_birthday, su_id, "MM-DD"),
    ...
]
```

### Adjust Grading Points

Edit `POINTS` dictionary:
```python
POINTS = {
    "process_startup": 5,
    "gcd_join": 10,
    ...
}
```

### Add New Criteria

1. Add entry to `POINTS` dictionary
2. Implement detection logic in `analyze_and_grade()`
3. Update scoring logic

## Notes

- The script uses pattern matching for automatic argument detection
- Each student's submission runs in isolation with a fresh GCD instance
- Processes are given time to communicate and elect leaders
- Extra credit is only awarded if patterns are detected multiple times
- Network communication is simulated on localhost to avoid firewall issues

## Support

For issues or questions:
1. Check that `gcd2.py` is the correct version
2. Verify student folder structure
3. Review `folder_args.md` for argument patterns
4. Check console output for specific errors
