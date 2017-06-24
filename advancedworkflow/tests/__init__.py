# -*- coding: utf-8 -*-

import unittest

def test_suite():
    from advancedworkflow.tests import controller
    suite = unittest.TestSuite()
    suite.addTest(controller.test_suite())
    return suite
