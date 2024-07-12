import pypeerassets.at.dt_misc_utils as mu
import json
from pypeerassets.provider import RpcNode, SlmRpcNode
from pypeerassets.__main__ import find_all_valid_cards, find_deck
from .at_dt_dummy_classes import TestObj

# Note: These tests need a running client daemon (peercoind, slimcoind).
# To conduct these tests, you need to rename the settings.default.json to settings.json.
# Then store your rpcuser, rpcpassword and port (default 9904) in this file.
# Take them from the cryptocurrency configuration file, e.g. peercoin.conf or slimcoin.conf.

with open("settings.json", "r") as settingsfile:
    settings = json.load(settingsfile)

########
## DT ##
########

# constants
PPC_DT_DECK_ID = "617005e36d23794763521ac3bad6d53a0ad6ee4259c8e45d8e81cdd09d67d595" # epoch length 22 blocks
PPC_SDP_DECK_ID = "7ffb89b247a91cc1759885442bacfdbbaf27d1a3329d998abc5072f8ef3ea110"
PPC_PROPOSAL_TXID = "697a33f5fdeeef1d136e342ecce6f42dd7aa16a3eb57b6f9273c5692dec74799"
SLM_DT_DECK_ID = "a2459e054ce0f600c90be458915af6bad36a6863a0ce0e33ab76086b514f765a" # "standard" dpod for SLM testnet
SLM_SDP_DECK_ID = "fb93cce7aceb9f7fda228bc0c0c2eca8c56c09c1d846a04bd6a59cae2a895974" # "standard" PoB token for SLM testnet
SLM_PROPOSAL_TXID = "37e7f1556c5e192ac782e3576b5723492daebdb884e1ce0a6d8aa89867194595" # "memecoins" proposal

if settings["network"] == "tppc":
    DT_DECK_ID, SDP_DECK_ID, PROPOSAL_TXID = PPC_DT_DECK_ID, PPC_SDP_DECK_ID, PPC_PROPOSAL_TXID
    PROVIDER = RpcNode(testnet=True, username=settings["rpcuser"], password=settings["rpcpass"], ip=None, port=settings["port"], directory=None)
elif settings["network"] == "tslm":
    DT_DECK_ID, SDP_DECK_ID, PROPOSAL_TXID = SLM_DT_DECK_ID, SLM_SDP_DECK_ID, SLM_PROPOSAL_TXID
    PROVIDER = SlmRpcNode(testnet=True, username=settings["rpcuser"], password=settings["rpcpass"], ip=None, port=settings["port"], directory=None)

# provider (needs running node)

# objects
SDP_DECK_OBJ = find_deck(PROVIDER, SDP_DECK_ID, 1, True)
DT_DECK_OBJ = find_deck(PROVIDER, DT_DECK_ID, 1, True)

# P2TH addresses
DT_DECK_P2TH = DT_DECK_OBJ.p2th_address # "mg5tRy8UUD5H1pwiyZnjeNzTdtfFrX6d1n"
P2TH_DONATION = DT_DECK_OBJ.derived_p2th_address("donation")
P2TH_LOCKING = DT_DECK_OBJ.derived_p2th_address("locking")
P2TH_SIGNALLING = DT_DECK_OBJ.derived_p2th_address("signalling")
P2TH_PROPOSAL = DT_DECK_OBJ.derived_p2th_address("proposal")
P2TH_VOTING = DT_DECK_OBJ.derived_p2th_address("voting")

# Import P2TH addresses, if still not done
mu.import_p2th_address(PROVIDER, P2TH_DONATION, accountname=DT_DECK_ID + "DONATION", wif_key=DT_DECK_OBJ.derived_p2th_wif("donation"))
mu.import_p2th_address(PROVIDER, P2TH_LOCKING, accountname=DT_DECK_ID + "LOCKING", wif_key=DT_DECK_OBJ.derived_p2th_wif("locking"))
mu.import_p2th_address(PROVIDER, P2TH_SIGNALLING, accountname=DT_DECK_ID + "SIGNALLING", wif_key=DT_DECK_OBJ.derived_p2th_wif("signalling"))
mu.import_p2th_address(PROVIDER, P2TH_PROPOSAL, accountname=DT_DECK_ID + "PROPOSAL", wif_key=DT_DECK_OBJ.derived_p2th_wif("proposal"))
mu.import_p2th_address(PROVIDER, P2TH_VOTING, accountname=DT_DECK_ID + "VOTING", wif_key=DT_DECK_OBJ.derived_p2th_wif("voting"))

PST_PROPOSAL = TestObj(all_donation_txes = [], all_signalling_txes = [], all_locking_txes = [], first_ptx = TestObj(txid = PROPOSAL_TXID))
SDP_CARDS = find_all_valid_cards(PROVIDER, SDP_DECK_OBJ)

# Voting (negative and positive votes). Dummy transactions.
NEGTX = [ TestObj(sender = "mnm7c3LcfkZGSwHZXpDBAZc67ugUgd3E3X", epoch=20000), TestObj(sender = "mybLEsXFH6emUt54bS3tci45d8vakZhdVT", epoch=19000) ]
POSTX = [ TestObj(sender = "miC3Vsh2WeZzmrzCRJuu5T7q9snvGvB353", epoch=20000)]
VOTINGTX = { PROPOSAL_TXID : { "negative" : NEGTX, "positive" : POSTX }}
VOTERS = {"mnm7c3LcfkZGSwHZXpDBAZc67ugUgd3E3X" : 5, "mybLEsXFH6emUt54bS3tci45d8vakZhdVT" : 5, "miC3Vsh2WeZzmrzCRJuu5T7q9snvGvB353" : 9}
PST = TestObj(proposal_states={PROPOSAL_TXID: PST_PROPOSAL}, deck=DT_DECK_OBJ, epoch=22008, sdp_cards=list(SDP_CARDS), voting_txes = VOTINGTX, enabled_voters=VOTERS)
