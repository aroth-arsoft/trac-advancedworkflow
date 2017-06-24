#!/usr/bin/env python
#
# Copyright (C) 2008-2014 Eli Carter <elicarter@retracile.net>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution.

from setuptools import setup, find_packages

extra = {}
try:
    import babel
    del babel
    extra['message_extractors'] = {
        'advancedworkflow': [
            ('**.py', 'python', None),
            ('**.html', 'genshi', None),
        ],
    }
    from trac.util.dist import get_l10n_cmdclass
    extra['cmdclass'] = get_l10n_cmdclass()
except ImportError:
    pass

setup(
    name='TracAdvancedTicketWorkflow',
    version='1.2.1',
    author='Eli Carter',
    author_email='elicarter@retracile.net',
    license='3-Clause BSD',
    description='Advanced workflow operations Trac plugin',
    long_description='Provides more advanced workflow operations for Trac 1.2',
    url='https://trac-hacks.org/wiki/AdvancedTicketWorkflowPlugin',

    packages=find_packages(),
    package_data={
        'advancedworkflow': [
            'locale/*/LC_MESSAGES/*.mo',
        ],
    },
    test_suite='advancedworkflow.tests.test_suite',
    entry_points={'trac.plugins': [
        'advancedworkflow.controller = advancedworkflow.controller'
    ]},
    install_requires=['Trac'],
    # zip_safe = False,
    **extra)
