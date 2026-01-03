# hbot

## Instruction for Contributors
1. Make sure `ruff` is installed
1. Before commiting, make sure to run `ruff check --fix && ruff format`

## How to Run
As seen in in [`main.py`](hbot/main.py#L13-L14), you need to export a
few variables.
```python
api_id = os.getenv("API_ID")
api_hash = os.getenv("API_HASH")
```
That is, `API_ID` and `API_HASH`. These can be obtained from *https://my.telegram.org/apps*.