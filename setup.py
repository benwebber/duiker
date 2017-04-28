# -*- coding: utf-8 -*-

import setuptools

setuptools.setup(
    name='duiker',
    version='0.1.0',
    url='https://github.com/benwebber/duiker/',

    description='Automatically index your shell history in a full-text search database. Magic!',
    long_description=open('README.rst').read(),

    author='Ben Webber',
    author_email='benjamin.webber@gmail.com',

    py_modules=['duiker'],

    zip_safe=False,

    entry_points={
        'console_scripts': [
            'duiker = duiker:main',
        ],
    },

    classifiers=[
        'Development Status :: 4 - Beta',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
    ],
)
