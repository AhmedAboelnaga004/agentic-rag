from services.rag.rewriter import rewrite_query



def build_effective_query(message: str) -> str:
    return rewrite_query(message)
