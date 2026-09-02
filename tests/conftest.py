import os
import tempfile


_TEST_RUNTIME = tempfile.TemporaryDirectory(prefix="bidproof-pytest-")
os.environ["BIDPROOF_DATA_ROOT"] = _TEST_RUNTIME.name
os.environ["BIDPROOF_ENV"] = "test"
os.environ["BIDPROOF_ALLOW_TRUSTED_HEADERS"] = "1"
