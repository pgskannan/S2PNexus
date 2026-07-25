# AI Configuration

The AI gateway uses environment-based settings defined through the shared settings object.

## Required settings

- `OLLAMA_BASE_URL`: Base URL for the Ollama API endpoint.
- `OLLAMA_MODEL`: Default model to use for generation and chat.
- `OLLAMA_TIMEOUT`: Request timeout in seconds for Ollama calls.
- `ENABLE_AI`: Enables the AI gateway endpoints.
- `ENABLE_RAG`: Enables retrieval-augmented generation features.

## Validation rules

- `OLLAMA_BASE_URL` must be a non-empty URL string.
- `OLLAMA_MODEL` must be a non-empty string.
- `OLLAMA_TIMEOUT` must be between `10` and `600` seconds.
- `ENABLE_AI` and `ENABLE_RAG` must be boolean values.

## Example

```env
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b
OLLAMA_TIMEOUT=120
ENABLE_AI=true
ENABLE_RAG=false
```
