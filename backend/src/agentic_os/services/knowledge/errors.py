"""Why a document could not be processed. The UI translates by `code`; `message` is the technical
detail (English) that goes to the log and under the document's error."""

from __future__ import annotations

# Codes (the UI has a sentence for each):
#   not_found      the original is not where it was
#   unsupported    a format the library does not read
#   encrypted      protected with a password
#   empty          no text and no images in it
#   too_large      bigger than the limit
#   url_error      the address could not be downloaded (message: the HTTP status or the reason)
#   convert_error  anything else the conversion raised
#   ocr_missing    (a warning, not a failure) the OCR model is not downloaded
#   embed_error    the embeddings failed
CODES = (
    "not_found",
    "unsupported",
    "encrypted",
    "empty",
    "too_large",
    "url_error",
    "convert_error",
    "ocr_missing",
    "embed_error",
)


class KnowledgeError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code
        self.message = message or code

    def as_dict(self) -> dict:
        return {"ok": False, "code": self.code, "message": self.message}
