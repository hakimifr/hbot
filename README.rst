hbot
####

.. note::
   If you ever plan on working with this codebase:

   #. Make sure `ruff`_ and `uv`_ is installed
   #. Before commiting, make sure to run ``ruff check --fix && ruff format``

   .. _ruff: https://astral.sh/ruff
   .. _uv: https://astral.sh/uv

How to Run
==========
As seen in |main.py|_, you need to export a few variables.

.. code-block:: python

   api_id = os.getenv("API_ID")
   api_hash = os.getenv("API_HASH")

That is, ``API_ID`` and ``API_HASH``. These can be obtained from *https://my.telegram.org/apps*.

Also, for the `Gemini plugin`_, you will need to export ``GEMINI_API_KEY``.
Without it, the bot won't crash, but the gemini plugin itself will log an error if you try to use
it.

.. |main.py| replace:: ``main.py``
.. _main.py: hbot/core/main.py#L15-L16
.. _Gemini plugin: hbot/plugins/gemini.py

Here's a snippet where that happens:

.. code-block:: python

   async def search_handler(self, client: Client, message: Message) -> None:
       if os.getenv(key="GEMINI_API_KEY") is None:
           await message.edit_text("api key for gemini is not set")
           logger.error("api key for gemini is not set, please export GEMINI_API_KEY")
           return

           [...snipped...]

Hosting
=======

The bot by default assume you have persistent storage at `/persist/storage`. However, should you
have the need to use a different path, export the variable ``PERSIST_DIR`` with the desired path.
All you configs will by saved by |jsondb|_ to the path.

.. |jsondb| replace:: ``jsondb``
.. _jsondb: https://github.com/hakimifr/jsondb
