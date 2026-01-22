# hbot

## Instruction for Contributors
1. Make sure `ruff` is installed
1. Before commiting, make sure to run `ruff check --fix && ruff format`

## How to Run
As seen in [`main.py`](hbot/core/main.py#L15-L16), you need to export a few variables.
```python
api_id = os.getenv("API_ID")
api_hash = os.getenv("API_HASH")
```

That is, `API_ID` and `API_HASH`. These can be obtained from *https://my.telegram.org/apps*.

Also, for the [Gemini plugin](hbot/plugins/gemini.py), you will need to export `GEMINI_API_KEY`.
Without it, the bot won't crash, but the gemini plugin itself will log an error if you try to use
it.

<details>
<summary>click to view snippet</summary>

```python
async def search_handler(self, client: Client, message: Message) -> None:
    if os.getenv(key="GEMINI_API_KEY") is None:
        await message.edit_text("api key for gemini is not set")
        logger.error("api key for gemini is not set, please export GEMINI_API_KEY")
        return
        
        [...snipped...]
```

</details>

## Hosting
The bot by default assume you have persistent storage at `/persist/storage`. However, should you
have the need to use a different path, export the variable `PERSIST_DIR` with the desired path.
All you configs will by saved by jsondb to the path.
