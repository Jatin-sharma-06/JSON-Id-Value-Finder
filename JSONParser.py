#!/usr/bin/env python3
"""
analyze_field.py

Parses a JSON file (single object or list of ticket-like objects) and
analyzes occurrences of a specific field ID inside each ticket's
`custom_fields` array and/or `fields` array.

Usage:
    python analyze_field.py path/to/file.json --field-id 360043617832
    python analyze_field.py path/to/file.json          # prompts for field ID

Standard library only: json, argparse, collections.
"""

import json
import argparse
import sys
from collections import Counter


def load_json(file_path):
    """
    Load and parse a JSON file. Supports two formats:
      1. A single JSON document (one object, or one array of objects).
      2. JSON Lines (JSONL) - one JSON object per line, common in
         ticket-system exports (e.g. Zendesk incremental exports).

    Returns the parsed object as a list of ticket dicts, or exits
    with a clear error message on failure.
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            raw = f.read()
    except FileNotFoundError:
        sys.exit(f"Error: file not found: {file_path}")
    except OSError as e:
        sys.exit(f"Error: could not read {file_path} -> {e}")

    # First, try parsing as a single JSON document.
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass  # fall through and try JSONL

    # Fall back to JSON Lines: one JSON object per non-empty line.
    tickets = []
    for line_num, line in enumerate(raw.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            tickets.append(json.loads(line))
        except json.JSONDecodeError as e:
            sys.exit(
                f"Error: invalid JSON in {file_path} at line {line_num} -> {e}\n"
                "(File is neither a single valid JSON document nor valid JSONL.)"
            )

    if not tickets:
        sys.exit(f"Error: no valid JSON content found in {file_path}")

    return tickets


def normalize_to_ticket_list(data):
    """
    The JSON root may be a single ticket object or a list of ticket
    objects. Normalize to a list either way.
    """
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return [data]
    sys.exit("Error: top-level JSON must be an object or a list of objects.")


def iter_field_entries(ticket):
    """
    Yield every field-entry dict found in a ticket's `custom_fields`
    array AND `fields` array (both are checked independently, per the
    spec's fallback wording; a ticket may legitimately have either,
    both, or neither).
    """
    for key in ("custom_fields", "fields"):
        entries = ticket.get(key)
        if isinstance(entries, list):
            for entry in entries:
                if isinstance(entry, dict):
                    yield entry


def analyze(tickets, field_id):
    """
    Walk every ticket and collect occurrences of field_id.

    Two lookup modes:
      1. Built-in top-level attribute: field_id given as "field:due_at"
         looks up ticket["due_at"] directly (for attributes like due_at,
         priority, status, subject - which are NOT inside custom_fields
         or fields arrays, they sit on the ticket object itself).
      2. Custom/agent field (default): field_id given as a plain ID,
         e.g. "360043617832", searches inside each ticket's
         custom_fields and fields arrays for a matching {"id": ...}.

    Returns:
        total_count (int)
        null_count (int)
        value_counter (Counter) - counts of non-null values, keyed by
                                   (type_name, value) to avoid bool/int
                                   hash collisions (True == 1 in Python).
    """
    total_count = 0
    null_count = 0
    value_counter = Counter()

    top_level_prefix = "field:"
    is_top_level_lookup = field_id.startswith(top_level_prefix)

    if is_top_level_lookup:
        attr_name = field_id[len(top_level_prefix):]

        for ticket in tickets:
            if not isinstance(ticket, dict):
                continue
            if attr_name not in ticket:
                continue  # ticket doesn't have this attribute at all

            value = ticket.get(attr_name)
            total_count += 1

            if value is None:
                null_count += 1
            else:
                if isinstance(value, list):
                    value = tuple(value)
                elif isinstance(value, dict):
                    # Built-in attributes can be nested objects (e.g.
                    # satisfaction_rating); represent them as JSON text
                    # so they're hashable and readable.
                    value = json.dumps(value, sort_keys=True)
                counter_key = (type(value).__name__, value)
                value_counter[counter_key] += 1

        return total_count, null_count, value_counter

    # --- Default mode: search custom_fields / fields arrays ---
    target_id = str(field_id)

    for ticket in tickets:
        if not isinstance(ticket, dict):
            continue  # skip malformed entries rather than crashing

        for entry in iter_field_entries(ticket):
            entry_id = entry.get("id")
            if entry_id is None:
                continue
            if str(entry_id) != target_id:
                continue

            total_count += 1
            value = entry.get("value")

            if value is None:
                null_count += 1
            else:
                # Lists (e.g. multi-select fields) aren't hashable directly;
                # normalize to a tuple so they can still be counted.
                if isinstance(value, list):
                    value = tuple(value)
                # Key by (type, value) rather than value alone. Python's
                # bool is a subclass of int, so True == 1 and False == 0 -
                # without the type tag, a boolean `true` and an integer `1`
                # would collide into the same Counter bucket.
                counter_key = (type(value).__name__, value)
                value_counter[counter_key] += 1

    return total_count, null_count, value_counter


def print_report(field_id, total_count, null_count, value_counter):
    """Print the analysis results in the requested format."""
    non_null_count = total_count - null_count

    print(f"Field ID: {field_id}")
    print(f"Total Occurrences : {total_count}")
    print(f"Null Values       : {null_count}")
    print(f"Non-Null Values   : {non_null_count}")

    if value_counter:
        print()
        print("Value Distribution:")
        print("-" * 20)
        # Keys are (type_name, value) tuples - see analyze(). Sort by
        # frequency (descending), then by displayed value for ties.
        for (type_name, value), count in sorted(
            value_counter.items(), key=lambda kv: (-kv[1], str(kv[0][1]))
        ):
            # Render using JSON-style casing (true/false, not True/False)
            # so it matches what you'd see grepping the raw file.
            if type_name == "bool":
                display = "true" if value else "false"
            elif type_name in ("int", "float"):
                display = str(value)
            elif isinstance(value, tuple):
                display = str(list(value))
            elif type_name == "str" and value.startswith(("{", "[")):
                # Already-serialized nested dict/list from a top-level
                # attribute (see analyze()) - print as-is, no double-quoting.
                display = value
            else:
                display = json.dumps(value)
            print(f"{display} : {count}")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Analyze occurrences of a specific field ID in a JSON ticket file."
    )
    parser.add_argument("json_file", help="Path to the JSON file to analyze.")
    parser.add_argument(
        "--field-id",
        "-f",
        dest="field_id",
        default=None,
        help="The field ID to search for. Two formats supported: "
        "a numeric custom/agent field ID (e.g. 360043617832), searched "
        "inside custom_fields/fields arrays; or a built-in top-level "
        "attribute using 'field:' prefix (e.g. field:due_at, field:priority, "
        "field:status), read directly off the ticket object. "
        "If omitted, you will be prompted for it.",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    field_id = args.field_id
    if not field_id:
        field_id = input("Enter field ID to analyze: ").strip()
        if not field_id:
            sys.exit("Error: no field ID provided.")

    data = load_json(args.json_file)
    tickets = normalize_to_ticket_list(data)

    total_count, null_count, value_counter = analyze(tickets, field_id)

    if total_count == 0:
        print(f"Field ID: {field_id}")
        print("No occurrences found for this field ID.")
        return

    print_report(field_id, total_count, null_count, value_counter)


if __name__ == "__main__":
    main()