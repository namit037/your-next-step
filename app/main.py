"""Your Next Step: entry point for the web API."""

from fastapi import FastAPI

app = FastAPI(
    title="Your Next Step",
    description="Search and compare careers using real public data.",
)


@app.get("/health")
def health() -> dict:
    """Tiny endpoint to check the server is running."""
    return {"status": "ok"}
