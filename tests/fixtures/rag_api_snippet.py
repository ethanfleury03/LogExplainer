from __future__ import absolute_import

# This fixture mimics the structure of backend/api.py
# It includes decorator + async def + docstring + match line

# Some leading code to make line numbers stable
import os
import sys

def some_other_function():
    """This function should NOT be selected."""
    x = 1
    return x


def _extract_document_sources():
    """This function should also NOT be selected for matches inside startup_event."""
    # Some code here
    y = 2
    return y


@app.on_event("startup")
async def startup_event():
    """FastAPI startup event handler.
    
    This function runs when the FastAPI application starts.
    It initializes the RAG index and handles any startup errors.
    """
    try:
        # Initialize RAG index
        logger.info("Starting RAG index initialization...")
        logger.error("[RAG] Index download failed during startup — RAG will be disabled")
        # More code here
        return True
    except Exception as e:
        logger.error("Startup error: %s" % (e,))
        return False


