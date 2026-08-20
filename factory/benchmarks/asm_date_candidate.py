"""Bounded, source-faithful candidate for the CardDemo COBDATFT HLASM routine."""

PROGRAM_ID = "COBDATFT"
INPUT_DATE_LENGTH = 20
OUTPUT_DATE_LENGTH = 20
ERROR_LENGTH = 38
INPUT_COMPACT = "1"
INPUT_HYPHENATED = "2"
OUTPUT_HYPHENATED = "1"
OUTPUT_COMPACT = "2"
INVALID_INPUT = "INVALID INPUT"


def format_date(input_type: str, input_date: str, output_type: str) -> dict[str, str]:
    """Mirror the byte-selection behavior in COBDATFT without broad date validation."""
    padded = input_date[:INPUT_DATE_LENGTH].ljust(INPUT_DATE_LENGTH)
    output = " " * OUTPUT_DATE_LENGTH
    error = " " * ERROR_LENGTH

    if input_type == INPUT_COMPACT:
        if padded[4:5] == "-" or output_type == OUTPUT_COMPACT:
            error = INVALID_INPUT.ljust(ERROR_LENGTH)
        else:
            output = f"{padded[:4]}-{padded[4:6]}-{padded[6:8]}".ljust(OUTPUT_DATE_LENGTH)
    elif input_type == INPUT_HYPHENATED:
        # The source's separator check is commented out, so offsets are preserved exactly.
        if output_type == OUTPUT_HYPHENATED:
            error = INVALID_INPUT.ljust(ERROR_LENGTH)
        else:
            output = f"{padded[:4]}{padded[5:7]}{padded[8:10]}".ljust(OUTPUT_DATE_LENGTH)
    else:
        error = INVALID_INPUT.ljust(ERROR_LENGTH)

    return {
        "input_type": input_type[:1],
        "input_date": padded,
        "output_type": output_type[:1],
        "output_date": output,
        "error_message": error,
    }
