def normalize_known_failure_test(test: str) -> str:
    return test.strip().replace("\\", "/")
