#!/usr/bin/env python
#
# Copyright (C) 2008-2014 Eli Carter <elicarter@retracile.net>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution.

from setuptools import setup, find_packages

setup(
    name='AdvancedTicketWorkflowPlugin',
    version='1.2.0',
    author='Eli Carter',
    author_email='elicarter@retracile.net',
    license='BSD',
    description='Advanced workflow operations Trac plugin',
    long_description='Provides more advanced workflow operations for Trac 1.2',
    url='http://trac-hacks.org/wiki/AdvancedTicketWorkflowPlugin',

    packages=find_packages(),
    package_data={},
    entry_points={'trac.plugins': [
        'advancedworkflow.controller = advancedworkflow.controller'
    ]},
    install_requires=[],
    # zip_safe = False,
)
