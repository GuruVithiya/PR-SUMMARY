def build_user_message(diff: str, pr_title: str = "", pr_description: str = "") -> str:
    """Build the user message to send to Bedrock with the diff context."""
    return f"""PR Title: {pr_title or 'N/A'}
PR Description: {pr_description or 'N/A'}

Code Diff:
```diff
{diff}
```

Analyse the diff and return the JSON response."""
