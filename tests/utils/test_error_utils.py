from deeptutor.utils.error_utils import public_error_detail


def test_public_error_detail_uses_generic_message() -> None:
    assert public_error_detail() == "Operation failed. Please try again later."


def test_public_error_detail_uses_operation_prefix() -> None:
    assert public_error_detail("Notebook operation") == "Notebook operation failed. Please try again later."
