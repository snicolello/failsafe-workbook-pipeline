"""A source-grounded refusal to accept one worksheet."""


OUTCOMES = {
    "processing_failure": "blocked",
    "structural_drift": "blocked",
    "ambiguous_columns": "blocked",
    "identity_ambiguity": "blocked",
    "unrecognized_value": "triaged",
}


class Rejection(Exception):
    """The original value is retained even when normalization fails."""

    def __init__(self, category: str, cell: str, value: object, message: str):
        super().__init__(message)
        if category not in OUTCOMES:
            raise ValueError(f"Unknown exception category: {category}")
        self.category = category
        self.cell = cell
        self.value = value
        self.message = message
        self.outcome = OUTCOMES[category]
