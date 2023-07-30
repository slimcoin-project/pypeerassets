from setuptools import setup

setup(name='pypeerassets',
      version='0.4.8-at',
      description='Python implementation of the PeerAssets protocol with support of AT tokens.',
      keywords=["blockchain", "digital assets", "protocol"],
      url='https://github.com/d5000/pypeerassets',
      author='PeerAssets team / Slimcoin team',
      author_email='peerchemist@protonmail.ch',
      license='BSD',
      packages=['pypeerassets', 'pypeerassets.provider', 'pypeerassets.at'],
      install_requires=['protobuf', 'peerassets-btcpy', 'peercoin_rpc']
      )
