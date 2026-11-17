import pymupdf

# Errors PyMuPDF raises for unreadable *input* (corrupted/truncated/garbage
# files). ``pymupdf.mupdf.FzErrorBase`` (e.g. FzErrorFormat "not a png
# image") derives directly from ``Exception``, not ``RuntimeError``, so it must
# be listed explicitly or a corrupted upload surfaces as HTTP 500 (BUG-016).
PYMUPDF_INPUT_ERRORS: tuple[type[BaseException], ...] = (
    pymupdf.EmptyFileError,
    pymupdf.FileDataError,
    pymupdf.mupdf.FzErrorBase,
    RuntimeError,
    ValueError,
)
