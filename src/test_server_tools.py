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

# Define reusable identifiers for the workflow
COMMON_RULE_TITLE = 45
COMMON_RULE_PART = "46"
COMMON_RULE_SECTION = "46.116"


def parse_json_maybe(text: str) -> dict | list | None:
    # Trim whitespace for JSON parsing
    trimmed = text.strip()

    # Return None for empty text
    if not trimmed:
        return None

    # Attempt to parse JSON text
    try:
        return json.loads(trimmed)
    except Exception:
        return None


def parse_status_and_message(stdout_text: str, stderr_text: str) -> tuple[str, str]:
    # Attempt to parse stdout as JSON first because the server returns structured payloads there
    stdout_json = parse_json_maybe(stdout_text)

    # Extract structured error details from stdout JSON when available
    if isinstance(stdout_json, dict):
        # Pull nested error payload when present
        error_payload = stdout_json.get("error")

        # Extract message from the nested error payload
        if isinstance(error_payload, dict):
            # Pull a human-readable message from common keys
            message = error_payload.get("message") or error_payload.get("detail") or error_payload.get("error")

            # Return the extracted message
            if message:
                return ("", str(message))

        # Pull a top-level message when present
        message = stdout_json.get("message") or stdout_json.get("detail")

        # Return the extracted top-level message
        if message:
            return ("", str(message))

        # Surface warnings when no direct message exists
        warnings = stdout_json.get("warnings")

        # Return a compact warning summary when present
        if isinstance(warnings, list) and warnings:
            return ("", "; ".join(str(item) for item in warnings[:3]))

    # Normalize stderr for JSON parsing
    stderr_trimmed = stderr_text.strip()

    # Try JSON on stderr
    try:
        parsed_err = json.loads(stderr_trimmed)

        # Handle dict-shaped JSON output
        if isinstance(parsed_err, dict):
            # Pull status from common keys
            status = parsed_err.get("http_status") or parsed_err.get("status") or parsed_err.get("status_code")

            # Normalize status to string
            status_str = "" if status is None else str(status)

            # Pull message from common keys
            msg = parsed_err.get("message") or parsed_err.get("error") or parsed_err.get("detail")

            # Normalize message to string
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

    # Build a compact stderr preview
    stderr_preview = stderr_trimmed.replace("\n", " ")[:240]

    # Build a compact stdout preview
    stdout_preview = stdout_text.strip().replace("\n", " ")[:240]

    # Prefer stderr preview when present
    if stderr_preview:
        return ("", stderr_preview)

    # Fall back to stdout preview when present
    return ("", stdout_preview)


def write_outputs(tool_name: str, completed: subprocess.CompletedProcess[str]) -> tuple[Path, Path]:
    # Define stdout file path
    out_path = RUN_DIR / f"{tool_name}.stdout.txt"

    # Define stderr file path
    err_path = RUN_DIR / f"{tool_name}.stderr.txt"

    # Persist stdout to file
    out_path.write_text(completed.stdout, encoding="utf-8")

    # Persist stderr to file
    err_path.write_text(completed.stderr, encoding="utf-8")

    # Return the output paths
    return out_path, err_path


def run_call(tool_name: str, tool_args: dict) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    # Convert args to compact JSON
    args_json = json.dumps(tool_args, separators=(",", ":"), ensure_ascii=False)

    # Build the client command
    cmd = [sys.executable, "client.py", "--server", "server.py", "--call", tool_name, "--args", args_json]

    # Execute the command
    completed = subprocess.run(cmd, capture_output=True, text=True)

    # Persist stdout and stderr to files
    out_path, err_path = write_outputs(tool_name, completed)

    # Return the execution result and output paths
    return completed, out_path, err_path


def write_summary_row(
    writer: csv.DictWriter,
    tool_name: str,
    tool_args: dict,
    completed: subprocess.CompletedProcess[str],
    out_path: Path,
    err_path: Path,
) -> None:
    # Convert args to compact JSON
    args_json = json.dumps(tool_args, separators=(",", ":"), ensure_ascii=False)

    # Parse the status and message fields
    http_status, message = parse_status_and_message(completed.stdout, completed.stderr)

    # Write the summary row
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


def pick_version_dates(versions_payload: dict) -> tuple[str, str]:
    # Pull the content versions array
    content_versions = versions_payload.get("content_versions", [])

    # Extract date strings from the version payloads
    dates = [item.get("date") for item in content_versions if isinstance(item, dict) and item.get("date")]

    # De-duplicate and sort dates in descending order
    unique_dates = sorted(set(dates), reverse=True)

    # Ensure at least one valid date exists
    if not unique_dates:
        raise RuntimeError("No valid dates returned by ecfr_get_title_versions")

    # Choose the latest available date
    latest_date = unique_dates[0]

    # Choose a previous date when available
    previous_date = unique_dates[1] if len(unique_dates) > 1 else unique_dates[0]

    # Return the two selected dates
    return latest_date, previous_date


# Open the summary CSV for writing
with summary_csv_path.open("w", newline="", encoding="utf-8") as f:
    # Create a CSV writer
    writer = csv.DictWriter(f, fieldnames=summary_columns)

    # Write the header row
    writer.writeheader()

    # Define initial tests that do not depend on discovered dates
    initial_tests = [
        ("ecfr_list_titles", {}),
        ("ecfr_list_agencies", {}),
        ("ecfr_search", {"query": "informed consent", "per_page": 3, "page": 1}),
        (
            "ecfr_get_title_versions",
            {"title": COMMON_RULE_TITLE, "part": COMMON_RULE_PART, "section": COMMON_RULE_SECTION, "limit": 10},
        ),
    ]

    # Cache total step count for progress tracking
    total_steps = 8

    # Execute the initial tests
    for index, (tool_name, tool_args) in enumerate(initial_tests, start=1):
        # Run the tool call
        completed, out_path, err_path = run_call(tool_name, tool_args)

        # Write the summary row
        write_summary_row(writer, tool_name, tool_args, completed, out_path, err_path)

        # Calculate percent completion
        percent_complete = round((index / total_steps) * 100, 2)

        # Emit progress update
        print(f"[{index}/{total_steps}] {percent_complete}% complete")

    # Re-run the versions call to capture stdout for dependency resolution
    versions_args = {"title": COMMON_RULE_TITLE, "part": COMMON_RULE_PART, "section": COMMON_RULE_SECTION, "limit": 10}

    # Execute the versions call used for downstream dates
    versions_completed, versions_out_path, versions_err_path = run_call("ecfr_get_title_versions", versions_args)

    # Write an additional summary row for the dependency-resolution call
    write_summary_row(writer, "ecfr_get_title_versions", versions_args, versions_completed, versions_out_path, versions_err_path)

    # Emit progress for the dependency-resolution step
    print(f"[5/{total_steps}] {round(5 / total_steps * 100, 2)}% complete")

    # Parse the versions payload from stdout
    versions_payload = parse_json_maybe(versions_completed.stdout)

    # Validate the parsed payload type
    if not isinstance(versions_payload, dict):
        raise RuntimeError("ecfr_get_title_versions returned non-JSON or unexpected JSON")

    # Choose valid dates for dependent tests
    latest_date, previous_date = pick_version_dates(versions_payload)

    # Define the dependent tests using discovered valid dates
    dependent_tests = [
        ("ecfr_get_title_structure", {"title": COMMON_RULE_TITLE, "date": latest_date, "depth": 2}),
        (
            "ecfr_compare_regulations",
            {
                "title": COMMON_RULE_TITLE,
                "part": COMMON_RULE_PART,
                "section": COMMON_RULE_SECTION,
                "date_1": previous_date,
                "date_2": latest_date,
            },
        ),
        (
            "ecfr_get_regulation",
            {
                "title": COMMON_RULE_TITLE,
                "part": COMMON_RULE_PART,
                "section": COMMON_RULE_SECTION,
                "date": latest_date,
            },
        ),
    ]

    # Execute dependent tests with continued progress indexing
    for offset, (tool_name, tool_args) in enumerate(dependent_tests, start=len(initial_tests) + 2):
        # Run the tool call
        completed, out_path, err_path = run_call(tool_name, tool_args)

        # Write the summary row
        write_summary_row(writer, tool_name, tool_args, completed, out_path, err_path)

        # Calculate percent completion
        percent_complete = round((offset / total_steps) * 100, 2)

        # Emit progress update
        print(f"[{offset}/{total_steps}] {percent_complete}% complete")

# Print final output locations
print(f"Wrote results to: {RUN_DIR}")

# Print the summary CSV location
print(f"Summary CSV: {summary_csv_path}")