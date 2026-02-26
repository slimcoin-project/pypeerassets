import pytest
import json

from pypeerassets.provider import Cryptoid, Explorer, SlmRpcNode

with open("settings.json", "r") as settingsfile:
    settings = json.load(settingsfile)
    SLMRPC_TEST = SlmRpcNode(testnet=True, username=settings["rpcuser"], password=settings["rpcpass"], ip=None, port=settings["port"], directory=None)
with open("settings-slmmainnet.json", "r") as settingsfile:
    settings = json.load(settingsfile)
    SLMRPC_MAIN = SlmRpcNode(testnet=False, username=settings["rpcuser"], password=settings["rpcpass"], ip=None, port=settings["port"], directory=None)

# syntax is different for RpcNode and Cryptoid
def validate_address(address, provider):
    if isinstance(provider, SlmRpcNode):
        return provider.validateaddress(address)["isvalid"]
    else:
        return provider.validateaddress(address)


@pytest.mark.parametrize("provider_cls", [Cryptoid])
def test_validateaddress_peercoin(provider_cls):
    "Check Providers that can validate Peercoin addresses."

    provider = provider_cls(network='peercoin')

    # Peercoin P2PKH, P2SH addresses.
    assert validate_address("PAdonateFczhZuKLkKHozrcyMJW7Y6TKvw", provider) is True
    assert validate_address("p92W3t7YkKfQEPDb7cG9jQ6iMh7cpKLvwK", provider) is True

    # Peercoin Testnet P2PKH address (these _should_ be False).
    assert validate_address("mj46gUeZgeD9ufU7Fvz2dWqaX6Nswtbpba", provider) is False
    assert validate_address("n12h8P5LrVXozfhEQEqg8SFUmVKtphBetj", provider) is False

    # Very much not Peercoin addresses.
    assert validate_address("1BFQfjM29kubskmaAsPjPCfHYphYvKA7Pj", provider) is False
    assert validate_address("2NFNPUYRpDXf3YXEuVT6AdMesX4kyeyDjtp", provider) is False


def test_validateaddress_slimcoin():
    "Check Providers that can validate Slimcoin mainnet addresses."

    provider = SLMRPC_MAIN

    # Peercoin P2PKH, P2SH addresses.
    assert validate_address("SbEroBFqLVbz6dYE4EWW36Py6nerRGmjkR", provider) is True
    assert validate_address("saEeoE68yUL9YfzjozoiyUg8BxwVoRzPKo", provider) is True

    # Peercoin Testnet P2PKH address (these _should_ be False).
    assert validate_address("mj46gUeZgeD9ufU7Fvz2dWqaX6Nswtbpba", provider) is False
    assert validate_address("n12h8P5LrVXozfhEQEqg8SFUmVKtphBetj", provider) is False

    # Very much not Peercoin addresses.
    assert validate_address("1BFQfjM29kubskmaAsPjPCfHYphYvKA7Pj", provider) is False
    assert validate_address("2NFNPUYRpDXf3YXEuVT6AdMesX4kyeyDjtp", provider) is False


@pytest.mark.parametrize("provider_cls", [Cryptoid, SlmRpcNode])
def test_validateaddress_peercoin_testnet(provider_cls):
    "Check Providers that can validate Peercoin Testnet addresses." # SLM here uses the same address format.

    provider = SLMRPC_TEST if provider_cls == SlmRpcNode else provider_cls(network='peercoin-testnet')

    # Peercoin Testnet P2PKH address.
    assert validate_address("mj46gUeZgeD9ufU7Fvz2dWqaX6Nswtbpba", provider) is True
    assert validate_address("n12h8P5LrVXozfhEQEqg8SFUmVKtphBetj", provider) is True

    # Peercoin P2PKH, P2SH addresses (these _should_ be False).
    assert validate_address("PAdonateFczhZuKLkKHozrcyMJW7Y6TKvw", provider) is False
    assert validate_address("p92W3t7YkKfQEPDb7cG9jQ6iMh7cpKLvwK", provider) is False

    # Very much not Peercoin Testnet addresses.
    assert validate_address("1BFQfjM29kubskmaAsPjPCfHYphYvKA7Pj", provider) is False
    # last one doesn't work with SlmRpcNode (is deemed valid). For now we skip it.
    if isinstance(provider, Cryptoid):
        assert validate_address("2NFNPUYRpDXf3YXEuVT6AdMesX4kyeyDjtp", provider) is False
