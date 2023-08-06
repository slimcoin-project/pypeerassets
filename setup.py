from setuptools import setup

setup(name='pypeerassets',
      version='0.4.8+slm',
      description='Python implementation of the PeerAssets protocol with support for Slimcoin and AT/PoB/dPoD tokens.',
      keywords=["blockchain", "digital assets", "protocol"],
      url='https://github.com/slimcoin-project/pypeerassets',
      author='PeerAssets team / Slimcoin team',
      author_email='peerchemist@protonmail.ch',
      license='BSD',
      packages=['pypeerassets', 'pypeerassets.provider', 'pypeerassets.at'],
      install_requires=['protobuf', 'peerassets-btcpy', 'peercoin_rpc']
      )
