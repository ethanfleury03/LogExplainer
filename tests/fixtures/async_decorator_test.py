from __future__ import absolute_import

# This fixture tests async def with decorator and multiple defs before it
# The match should be attributed to async def startup_event(), not earlier defs
# Match line is at line 20 (logger.error)

def _extract_document_sources():
    """This function should NOT be selected for matches inside startup_event."""
    x = 1
    y = 2
    return x + y


def another_function():
    """This function should also NOT be selected."""
    logger.info("Some other log")
    return None


@app.on_event("startup")
async def startup_event():
    """This is the correct enclosure for the match at line 20."""
    logger.error("[RAG] Index download failed...")
    # More code here
    return True

