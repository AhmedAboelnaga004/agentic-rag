def chunking_strategy_name(technique: str) -> str:
    if technique == "llamaparse":
        return "markdown-header-plus-recursive"
    return "vision-markdown-plus-recursive"
