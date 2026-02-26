import pytest
import pypeerassets as pa
from pypeerassets.__main__ import find_card_bundles, get_card_transfer
from pypeerassets.protocol import CardBundle, CardTransfer
from pypeerassets.provider import Explorer, Cryptoid, SlmRpcNode
from btcpy.structs.transaction import MutableTransaction
from pypeerassets.transactions import Transaction

with open("settings.json", "r") as settingsfile: # TODO: the settings.json file should not be necessary. We could use pacli.Settings but better not depend on pacli here?
    import json
    settings = json.load(settingsfile)
    SLMRPC = SlmRpcNode(testnet=True, username=settings["rpcuser"], password=settings["rpcpass"], ip=None, port=settings["port"], directory=None)
    SLM_TESTNET_DECKID = "fb93cce7aceb9f7fda228bc0c0c2eca8c56c09c1d846a04bd6a59cae2a895974"


@pytest.mark.parametrize("prov", [Cryptoid, SlmRpcNode])
def test_find_deck(prov):

    if prov == SlmRpcNode:
        provider = SLMRPC
        deckid = SLM_TESTNET_DECKID
        deck_json = {'version': 1,
                     'name': 'ATTokenNewSpec2',
                     'issue_mode': 1,
                     'number_of_decimals': 4,
                     'asset_specific_data': b'\x10\x02@dJ\x14@\xf1c\xa4\xd0\xa8\xbcD\xb4\xba\x00\xb9T\xc2\xbd\xbe\xfb\x87|\xf4P\x02',
                     'id': 'fb93cce7aceb9f7fda228bc0c0c2eca8c56c09c1d846a04bd6a59cae2a895974',
                     '_p2th_wif': 'cW1jbDP9JQ9GhN7EYofZbUifigbsm6rgUHayXpNVN9kQoKuzoSGM',
                     'p2th_wif': 'cW1jbDP9JQ9GhN7EYofZbUifigbsm6rgUHayXpNVN9kQoKuzoSGM', # TODO: this doubling should not be necessary.
                     'issuer': 'mvrm2HAoKqiCmeQiwKMuEFpeEn7rJEmpMz',
                     'issue_time': 1679503968,
                     'tx_confirmations': 100, # see below
                     'network': 'tslm',
                     'production': True,
                     'at_type': 2,
                     'multiplier': 100,
                     'at_address': 'mmSLiMCoinTestnetBurnAddress1XU5fu',
                     'addr_type': 2,
                     'startblock': None,
                     'endblock': None,
                     'extradata': None
                     }
    else:
        pytest.skip("Cryptoid currently incompatible with code.")
        provider = prov(network="tppc")
        deckid = 'b6a95f94fef093ee9009b04a09ecb9cb5cba20ab6f13fe0926aeb27b8671df43'
        deck_json = {'asset_specific_data': b'',
                     'id': deckid,
                     'issue_mode': 4,
                     'issue_time': 1488840533,
                     'issuer': 'msYThv5bf7KjhHT1Cj5D7Y1tofyhq9vhWM',
                     'name': 'hopium_v2',
                     'network': 'peercoin-testnet',
                     'number_of_decimals': 2,
                     'production': True,
                     'version': 1,
                     'tx_confirmations': 100,
                     'p2th_wif': 'cThmj6Qu6aTUeA5f4FoNJTsBA8K6ZjhXbZkwsqcmv94xjWiCBr5d'
                     }

    deck = pa.find_deck(provider, deckid, 1)

    deck.tx_confirmations = 100  # make it deterministic

    assert deck.to_json() == deck_json

def test_find_card_bundles():

    # provider = Explorer(network="tppc")
    # deckid = 'adc6d888508ebfcad5c182df4ae94553bae6287735d76b8d64b3de8d29fc2b5b'
    provider = SLMRPC
    deckid = SLM_TESTNET_DECKID
    deck = pa.find_deck(provider, deckid, 1)

    bundles = find_card_bundles(provider, deck)

    assert bundles
    assert isinstance(next(bundles), CardBundle)


@pytest.mark.parametrize("prov", [SlmRpcNode, Cryptoid])
def test_get_card_bundles(prov):

    if prov == SlmRpcNode:
        provider = SLMRPC
        deckid = SLM_TESTNET_DECKID
    else:
        pytest.skip("Cryptoid currently incompatible with code.")
        provider = prov(network="tppc")
        deckid = 'b6a95f94fef093ee9009b04a09ecb9cb5cba20ab6f13fe0926aeb27b8671df43'

    deck = pa.find_deck(provider, deckid, 1)

    bundles = pa.get_card_bundles(provider, deck)

    assert bundles
    assert isinstance(list(next(bundles))[0], pa.CardTransfer)


def test_get_card_transfer():
    '''test finding a single card tranfer'''

    # provider = Explorer(network="tppc")
    # deckid = '98694bb54fafe315051d2a8f1f5ea4c0050947741ced184a5f33bf4a0081a0bb'
    # txid = 'e04fb602bd9d9c33d1d1af8bb680108057c2ae37ea987cc15295cc6fc4fd8d97'
    provider = SLMRPC
    deckid = SLM_TESTNET_DECKID
    txid = '909863ab0e1c0f62cc0c6721bea140c2d0618d9dd7f4e7bd05ff735ce92cc1a6'

    deck = pa.find_deck(provider, deckid, 1, True)

    card = list(get_card_transfer(provider, deck, txid))

    assert isinstance(card[0], CardTransfer)


@pytest.mark.parametrize("prov", [SlmRpcNode, Cryptoid])
def test_find_all_valid_cards(prov):

    if prov == SlmRpcNode:
        provider = SLMRPC
        deckid = SLM_TESTNET_DECKID
    else:
        pytest.skip("Cryptoid currently incompatible with code.")
        provider = prov(network="tppc")
        deckid = 'b6a95f94fef093ee9009b04a09ecb9cb5cba20ab6f13fe0926aeb27b8671df43'

    deck = pa.find_deck(provider, deckid, 1)

    cards = pa.find_all_valid_cards(provider, deck)

    assert cards
    assert isinstance(next(cards), pa.CardTransfer)


def test_deck_spawn():

    # provider = Explorer(network='tppc')
    # issuer = "mthKQHpr7zUbMvLcj8GHs33mVcf91DtN6L"
    # network = 'tppc'
    provider = SLMRPC
    issuer = "mxXYivKBsdM3udEMQMJVu3xAxnWthFuGZN" # same as in test_kutil, keep it funded
    network = "tslm"
    inputs = provider.select_inputs(issuer, 0.02)
    change_address = issuer
    deck = pa.Deck(name="just-testing.", number_of_decimals=1, issue_mode=1,
                   network=network, production=True, version=1,
                   asset_specific_data='https://talk.peercoin.net/')

    deck_spawn = pa.deck_spawn(provider, deck, inputs, change_address)

    assert isinstance(deck_spawn, MutableTransaction)


def test_card_transfer():

    # provider = Explorer(network='tppc')
    # address = "mthKQHpr7zUbMvLcj8GHs33mVcf91DtN6L"
    # deckid = '078f41c257642a89ade91e52fd484c141b11eda068435c0e34569a5dfcce7915'
    # receivers = ['n12h8P5LrVXozfhEQEqg8SFUmVKtphBetj', 'n422r6tcJ5eofjsmRvF6TcBMigmGbY5P7E']
    provider = SLMRPC
    address = "mxXYivKBsdM3udEMQMJVu3xAxnWthFuGZN"
    receivers = ['mq7Gu9rYPa9sTDCQd3EAubtG2oskSVzhz9', 'mjUNNZkEQFXfWtx8h2aHFF9KV2bR2iSNL5']
    deckid = SLM_TESTNET_DECKID

    inputs = provider.select_inputs(address, 0.02)
    change_address = address
    deck = pa.find_deck(provider,
                         deckid,
                         1, True)
    card = pa.CardTransfer(deck=deck,
                           receiver=receivers,
                           amount=[1, 2]
                           )

    card_transfer = pa.card_transfer(provider, card, inputs, change_address,
                                     locktime=300000)

    assert isinstance(card_transfer, Transaction)
