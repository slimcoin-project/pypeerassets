## contains functions for legacy clients/blockchains like Slimcoin
## these chains lack some modern features or have other limitations

from pypeerassets.provider import Provider
from pypeerassets.exceptions import P2THImportFailed

## mintx: chains who have a minimum transaction amount.
## watchonly: chains who can't import watchonly addresses
## : chains who need a min_tx_fee value even in OP_RETURN outputs.

LEGACY_CHAINS = { "mintx" : ("slm", "tslm", "ppc", "tppc"),
                 "nulldata" : ("slm", "tslm"),
                 "watchonly" : ("slm", "tslm") }

LEGACY_MINTX = { ("slm", "tslm", "tppc") : 10000,
                 ("ppc") : 1000 }

def is_legacy_blockchain(network_shortname, item="watchonly"):
    # this help function returns blockchains who do not support watch addresses and need the WIF key to import
    # P2TH addresses into the client.
    # item is the "deficiency" the legacy version has.

    result = network_shortname in LEGACY_CHAINS.get(item)
    return result

def legacy_import(provider: Provider, p2th_address: str, p2th_wif: str, rescan: bool=False, silent: bool=False, accountname: str=None) -> None:

    if accountname is None:
        accountname = p2th_address # previous behavior

    if not silent:
        print("Legacy blockchain import, imports WIF key.")
    # this checks if a P2TH address is already imported. If not, import it (only rpcnode).
    p2th_account = provider.getaccount(p2th_address)

    if (type(p2th_account) == dict) and (p2th_account.get("code") == -5):
        # raise ValueError("Invalid address.")
        raise DeckP2THImportError("Invalid address")

    if (p2th_account is None) or (p2th_account != accountname): # p2th_address changed to accountname
        provider.importprivkey(p2th_wif, accountname)
        # provider.setaccount(p2th_address, p2th_address) # address is also the account name. # TODO recheck why this line existed
        check_addr = provider.validateaddress(p2th_address)

        if not check_addr["isvalid"] and not check_addr["ismine"]:
            raise P2THImportFailed(error)

def legacy_mintx(network_shortname):
    for key in LEGACY_MINTX:
        if network_shortname in key:
            return LEGACY_MINTX[key]
    return None

