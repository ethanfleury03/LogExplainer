from __future__ import absolute_import

# This is a comment header above the function (not a docstring)
# It provides context about what the function does

@app.on_event("startup")
async def startup_event_with_docstring():
    """This is the real Python docstring inside the function.
    
    It explains what the function does.
    More details here.
    """
    logger.error("[RAG] Index download failed...")
    return True


# Header comment for this function
def function_with_comment_header():
    # This function has a comment header above but no docstring
    logger.error("Some error message")
    return None


"""This is a triple-quote header block above the function.
It's not a docstring, just a comment block.
"""

def function_with_header_block():
    """This is the actual docstring inside the function, different from header."""
    logger.error("Another error")
    return True


