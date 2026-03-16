import csv
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Create an output directory for test artifacts
LOG_DIR = Path("../test_outputs/server_tests")
# Ensure the output directory exists
LOG_DIR.mkdir(parents=True, exist_ok=True)
# Create a timestamp for this run
RUN_TS = datetime.now().strftime("%Y%m%d_%H%M%S")
# Create a run-specific directory
RUN_DIR = LOG_DIR / RUN_TS
# Ensure the run directory exists
RUN_DIR.mkdir(parents=True, exist_ok=True)

def run_tool(tool_name: str, tool_args: dict) -> subprocess.CompletedProcess:
    # Convert args to JSON
    args_json = json.dumps(tool_args, separators=(",", ":"), ensure_ascii=False)
    # Build the client command
    cmd = [sys.executable, "client.py", "--server", "server.py", "--call", tool_name, "--args", args_json]
    # Execute the command
    return subprocess.run(cmd, capture_output=True, text=True)

def parse_json_output(stdout_text: str) -> dict:
    # Parse stdout text as JSON
    return json.loads(stdout_text.strip())

def pick_version_dates(version_payload: dict) -> tuple[str, str]:
    # Pull content versions from the payload
    content_versions = version_payload.get("content_versions", [])
    # Keep only entries that contain a date
    dated_versions = [item for item in content_versions if isinstance(item, dict) and item.get("date")]
    # Fail when no valid dates are available
    if not dated_versions:
        raise ValueError("No valid dates returned from ecfr_get_title_versions")
    # Sort dates from oldest to newest
    dated_versions.sort(key=lambda item: item["date"])
    # Pick the latest date for current lookups
    latest_date = dated_versions[-1]["date"]
    # Pick an earlier date for comparison when possible
    earlier_date = dated_versions[-2]["date"] if len(dated_versions) > 1 else latest_date
    # Return the selected dates
    return earlier_date, latest_date

# Get valid dates first for versioned tools
version_lookup_args = {"title": 45, "part": "46", "section": "46.116", "limit": 10}
version_lookup_completed = run_tool("ecfr_get_title_versions", version_lookup_args)
version_lookup_payload = parse_json_output(version_lookup_completed.stdout)
compare_date_1, valid_date = pick_version_dates(version_lookup_payload)

# Define tool calls and args
tests = [
    ("ecfr_list_titles", {"summary_only": True}),
    ("ecfr_list_agencies", {"include_children": False}),
    ("ecfr_search", {"query": "informed consent", "per_page": 3, "page": 1, "include_excerpts": False, "order": "relevance"}),
    ("ecfr_get_title_versions", {"title": 45, "part": "46", "section": "46.116", "limit": 10}),
    ("ecfr_get_title_structure", {"title": 45, "date": valid_date, "depth": 2}),
    ("ecfr_compare_regulations", {"title": 45, "part": "46", "section": "46.116", "date_1": compare_date_1, "date_2": valid_date, "include_full_text": False}),
    ("ecfr_get_regulation", {"title": 45, "part": "46", "section": "46.116", "date": valid_date, "text_only": True}),
]

# Cache total test count for progress tracking
total_tests = len(tests)

# Define the summary CSV output path
summary_csv_path = RUN_DIR / "summary.csv"
# Define columns for the summary output
summary_columns = [
    "run_stamp",
    "python_executable",
    "tool",
    "args_json",
    "returncode",
    "http_status",
    "message",
    "stdout_file",
    "stderr_file",
]

def parse_status_and_message(stdout_text: str, stderr_text: str) -> tuple[str, str]:
    # Normalize stderr for JSON parsing
    stderr_trimmed = stderr_text.strip()

    # Try JSON on stderr
    try:
        parsed_err = json.loads(stderr_trimmed)
        # Handle dict-shaped JSON output
        if isinstance(parsed_err, dict):
            # Pull status from common keys
            status = parsed_err.get("http_status") or parsed_err.get("status") or parsed_err.get("status_code")
            # Normalize to string
            status_str = "" if status is None else str(status)
            # Pull message from common keys
            msg = parsed_err.get("message") or parsed_err.get("error") or parsed_err.get("detail")
            # Normalize to string
            msg_str = "" if msg is None else str(msg)
            # Return extracted values
            return (status_str, msg_str)
    except Exception:
        # Fall through to plain-text parsing
        pass

    # Find the last HTTP status token sequence in stderr
    http_marker = "HTTP/"
    # Locate the last occurrence of the marker
    marker_index = stderr_trimmed.rfind(http_marker)
    # Proceed only if the marker exists
    if marker_index != -1:
        # Find the first space after HTTP/x.y
        after_proto_space = stderr_trimmed.find(" ", marker_index)
        # Ensure there is a space after the protocol portion
        if after_proto_space != -1:
            # Slice the substring after the protocol space
            remainder = stderr_trimmed[after_proto_space + 1 :]
            # Ensure the remainder is long enough to hold a 3-digit code
            if len(remainder) >= 3:
                # Extract the first three characters as the status candidate
                code_candidate = remainder[:3]
                # Validate the candidate is digits
                if code_candidate.isdigit():
                    # Convert to int for range validation
                    code_int = int(code_candidate)
                    # Validate HTTP status code range
                    if 100 <= code_int <= 599:
                        # Find the next quote after the marker to bound the status phrase, if present
                        quote_start = stderr_trimmed.rfind('"', 0, marker_index)
                        # Find the quote end after the marker
                        quote_end = stderr_trimmed.find('"', marker_index)
                        # Compute a compact message from the quoted HTTP status line when possible
                        if quote_start != -1 and quote_end != -1 and quote_end > quote_start:
                            # Extract the quoted content
                            quoted = stderr_trimmed[quote_start + 1 : quote_end]
                            # Return status code and the quoted status line as message
                            return (str(code_int), quoted)
                        # Return status code with a short stderr preview
                        return (str(code_int), stderr_trimmed[:240].replace("\n", " "))

    # Fall back to previews when no HTTP marker is found
    stderr_preview = stderr_trimmed.replace("\n", " ")[:240]
    # Prefer stderr preview when present
    return ("", stderr_preview)

# Open the summary CSV for writing
with summary_csv_path.open("w", newline="", encoding="utf-8") as f:
    # Create a CSV writer
    writer = csv.DictWriter(f, fieldnames=summary_columns)
    # Write the header row
    writer.writeheader()

    # Iterate through tests with index for progress tracking
    for index, (tool_name, tool_args) in enumerate(tests, start=1):
        # Convert args to JSON
        args_json = json.dumps(tool_args, separators=(",", ":"), ensure_ascii=False)
        # Build the client command
        cmd = [sys.executable, "client.py", "--server", "server.py", "--call", tool_name, "--args", args_json]
        # Define stdout file path
        out_path = RUN_DIR / f"{tool_name}.stdout.txt"
        # Define stderr file path
        err_path = RUN_DIR / f"{tool_name}.stderr.txt"
        # Execute the command
        completed = subprocess.run(cmd, capture_output=True, text=True)
        # Persist stdout to file
        out_path.write_text(completed.stdout, encoding="utf-8")
        # Persist stderr to file
        err_path.write_text(completed.stderr, encoding="utf-8")

        # Parse status and message
        http_status, message = parse_status_and_message(completed.stdout, completed.stderr)

        # Write summary row
        writer.writerow(
            {
                "run_stamp": RUN_TS,
                "python_executable": sys.executable,
                "tool": tool_name,
                "args_json": args_json,
                "returncode": completed.returncode,
                "http_status": http_status,
                "message": message,
                "stdout_file": out_path.name,
                "stderr_file": err_path.name,
            }
        )

        # Calculate percent completion
        percent_complete = round((index / total_tests) * 100, 2)
        # Emit progress update
        print(f"[{index}/{total_tests}] {percent_complete}% complete")

# Print final output locations
print(f"Wrote results to: {RUN_DIR}")
print(f"Summary CSV: {summary_csv_path}")