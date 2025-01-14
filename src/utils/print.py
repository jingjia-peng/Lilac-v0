import subprocess


def print_info(
    *values: object,
):
    print("\033[92m", *values, "\033[0m", sep="")


def print_error(
    *values: object,
):
    print("\033[91m", *values, "\033[0m", sep="")


def print_cmd_result(result: subprocess.CompletedProcess):
    print_info("STDOUT:") if result.stdout else None
    print(result.stdout)
    print_error("STDERR:") if result.stderr else None
    print(result.stderr)
