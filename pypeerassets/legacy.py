## contains functions for legacy clients/blockchains like Slimcoin
## these chains lack some modern features or have other limitations

from pypeerassets.provider import Provider

## mintx: chains who have a minimum transaction amount.
## watchonly: chains who can't import watchonly addresses
## : chains who need a min_tx_fee value even in OP_RETURN outputs.

LEGACY_CHAINS = { "mintx" : ("slm", "tslm", "ppc", "tppc"),
                 "nulldata" : ("slm", "tslm"),
                 "watchonly" : ("slm", "tslm") }

LEGACY_MINTX = { ("slm", "tslm", "tppc") : 10000,
                 ("ppc") : 1000 }
# TODO: ppc and tppc values are from memory. re-check!

#LEGACY_MINTX = ("slm", "tslm")
#LEGACY_WATCHONLY = ("slm", "tslm")
#LEGACY_NULLDATA = ("slm", "tslm")



def is_legacy_blockchain(network_shortname, item="watchonly"):
    # this help function returns blockchains who do not support watch addresses and need the WIF key to import
    # P2TH addresses into the client.
    # item is the "deficiency" the legacy version has.

    #if item == "watchonly":
    #    legacy_chains = LEGACY_WATCHONLY
    #elif item == "nulldata":
    #    legacy_chains = LEGACY_NULLDATA
    #elif item == "mintx":
    #    legacy_chains = LEGACY_MINTX

    result = network_shortname in LEGACY_CHAINS.get(item)
    return result

def legacy_import(provider: Provider, p2th_address: str, p2th_wif: str, rescan: bool=False) -> None:

    print("Legacy blockchain import, imports WIF key.")
    # this checks if a P2TH address is already imported. If not, import it (only rpcnode).
    p2th_account = provider.getaccount(p2th_address)

    if (type(p2th_account) == dict) and (p2th_account.get("code") == -5):
        raise ValueError("Invalid address.")

    if (p2th_account is None) or (p2th_account != p2th_address):
        provider.importprivkey(p2th_wif, p2th_address)
        provider.setaccount(p2th_address, p2th_address) # address is also the account name.

def legacy_mintx(network_shortname):
    for key in LEGACY_MINTX:
        if network_shortname in key:
            return LEGACY_MINTX[key]
    return None

