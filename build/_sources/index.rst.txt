##################
hbot documentation
##################

.. important::
   This documentation is intended for myself, so is this hbot. But it is made in a very modular way,
   so you should be able to use this very easily (see `the plugins section`_). Should you
   have any trouble using this bot, you can `contact me`_ for help, but know that I might not always
   be able to help. (Please note in your message about this
   bot, otherwise I won't reply.

.. _contact me: https//t.me/hakimifr
.. _the plugins section: /plugins

Usage Instruction
=================

1. Clone the repo:

.. code-block:: sh

   git clone https://github.com/hakimifr/hbot
   cd hbot

2. Install dependencies (you will need `uv`_ for this):

.. code-block:: sh

   uv sync --frozen

3. Export the required variable:

.. code-block:: sh

   export API_id="<your api id>"
   export API_HASH="<your api hash>"
   export GEMINI_API_KEY="<your gemini api key>" # Optional, but required for gemini plugin to work

4. Run the bot!

.. code-block::

   uv run python3 -m hbot

.. _uv: https://astral.sh/uv

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   Working with plugins <plugins>
   Api Documentation <modules>
