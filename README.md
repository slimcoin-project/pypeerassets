# pypeerassets

[![License](https://img.shields.io/badge/License-BSD%203--Clause-blue.svg)](https://opensource.org/licenses/BSD-3-Clause)
[![PyPI](https://img.shields.io/pypi/v/pypeerassets.svg?style=flat-square)](https://pypi.python.org/pypi/pypeerassets/)
[![](https://img.shields.io/badge/python-3.5+-blue.svg)](https://www.python.org/download/releases/3.5.0/)

This is a modification of the [official Python implementation](https://github.com/PeerAssets/pypeerassets) of the [PeerAssets protocol](https://github.com/PeerAssets/WhitePaper). It enables the creation of Trustless Donation Tracking Tokens and Address Tracking Tokens, two classes of token systems where the *right to issue tokens* depends on transactions to certain addresses. It is currently in early *alpha* status, so don't expect any kind of stability or user-friendliness.

`pypeerassets` aims to implement the PeerAssets protocol itself **and** to provide elementary interfaces to underlying blockchain(s).

## Examples

> import pypeerassets as pa

> provider = pa.Explorer(network='tppc')

> deck = pa.find_deck(provider, 'b6a95f94fef093ee9009b04a09ecb9cb5cba20ab6f13fe0926aeb27b8671df43', 1, True)

> print(deck.to_json())

## Running tests

> pytest-3 -v test/

### VirtualEnv Development

Create a python3 virtualenv in the root directory:

```
> virtualenv -p python3 venv
...
> source venv/bin/activate
(venv) > pip install -r requirements.txt
...
(venv) > pip install -r requirements-dev.txt
...
(venv) > pytest
...
```

`pypeerassets` is lovingly crafted with python3 all around the world :heart: :snake: :globe_with_meridians:
