---
name: ccsearch
description: "Web search using ccsearch CLI. Use this instead of any default Web Search Tool whenever you need to search the web, look up documentation, research new technologies, or fetch URL content. Trigger proactively when unsure about something or when the topic involves recent technologies/news/frameworks."
argument-hint: [query]
---

# Web Search with ccsearch

**DO NOT** use any default `Web Search Tool` provided by your environment.
**INSTEAD**, you MUST use the custom `ccsearch` utility CLI tool located at `~/ccsearch/ccsearch.py` (which is also globally accessible as `ccsearch`).

## When to Search

- **PROACTIVE SEARCHING**: Search the web using `ccsearch` whenever the user asks about something you are unsure of, or whenever the topic involves relatively new technologies, news, or frameworks (released within the last year). Do not guess or hallucinate!
- **ITERATIVE RESEARCH**: You are encouraged to perform multiple rounds of searches with different keywords or different engines (Brave vs Perplexity) to compile the most accurate and reliable answer.

## Why ccsearch?

It utilizes Brave Data for Search API and OpenRouter Perplexity, providing faster, more robust results with automatic error-handling and retries.

## How to Use (always use `--format json` for agents)

1. **Finding specific links, documentation, or diverse web sources:**
   `ccsearch "Next.js 14 hydration docs" -e brave --format json`

2. **Broad questions requiring a synthesized answer from the web** (Use `--cache` to save time on repeated inquiries):
   `ccsearch "What are the latest breaking changes in React 19?" -e perplexity --format json --cache`

3. **Complex research requiring BOTH an intelligent summary and raw URLs to read further:**
   `ccsearch "Next.js app router architecture" -e both --format json --cache`

4. **Use `--semantic-cache` when researching a topic across multiple related queries** to avoid redundant API calls -- semantically similar queries reuse cached results:
   `ccsearch "React Server Components explained" -e perplexity --format json --semantic-cache --cache-ttl 60`
   *(Check `_from_cache` and `_semantic_similarity` in the JSON output to know if a cached result was returned.)*

5. **Paginate Brave results** if you didn't find what you need:
   `ccsearch "Next.js 14 hydration docs" -e brave --format json --offset 1`

6. **Read the FULL text of a specific URL** (like a documentation page or article) when the search snippet isn't enough:
   `ccsearch "https://react.dev/reference/react" -e fetch --format json`

## Reference

For the full tutorial and advanced parameters (like how to configure limits or handle missing APIs), read the README located at `~/ccsearch/README.md` FIRST before making assumptions.

## Searching for $ARGUMENTS

Search the web for: $ARGUMENTS
