# -*- coding: utf-8 -*-

from datetime import datetime
import unittest

from trac.test import EnvironmentStub, MockRequest
from trac.ticket.api import TicketSystem
from trac.ticket import model
from trac.ticket.model import Milestone, Ticket
from trac.ticket.web_ui import TicketModule
from trac.util.datefmt import to_utimestamp, utc
from trac.web.api import RequestDone

import advancedworkflow.controller


class AdvancedTicketWorkflowTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(default_data=True,
                                   enable=['trac.*', 'advancedworkflow.*'])
        self.tktmod = TicketModule(self.env)

    def tearDown(self):
        self.env.reset_db()

    def _config_set(self, section, entries):
        for option, value in entries:
            self.env.config.set(section, option, value)

    def _insert_ticket(self, when=None, **values):
        values.setdefault('status', 'new')
        values.setdefault('type', 'defect')
        ticket = Ticket(self.env)
        ticket.populate(values)
        return ticket.insert(when=when)

    def _insert_component(self, name, owner):
        component = model.Component(self.env)
        component.name = name
        component.owner = owner
        component.insert()

    def _post_req(self, action, ticket):
        form_token = 'x' * 40
        args = {'action': action, 'submit': '1', '__FORM_TOKEN': form_token,
                'view_time': str(to_utimestamp(ticket['changetime']))}
        args.update(('field_' + f['name'], ticket[f['name']])
                    for f in ticket.fields)
        return MockRequest(self.env, method='POST', form_token=form_token,
                           path_info='/ticket/%d' % ticket.id, args=args)

    def test_set_owner_to_reporter(self):
        self.env.config.set('ticket', 'workflow',
            'ConfigurableTicketWorkflow,TicketWorkflowOpOwnerReporter')
        self._config_set('ticket-workflow', [
            ('needinfo', '* -> needinfo'),
            ('needinfo.name', 'Need info'),
            ('needinfo.operations', 'set_owner_to_reporter'),
        ])
        tktid = self._insert_ticket(summary='set owner to reporter',
                                    reporter='john', owner='joe')
        ticket = Ticket(self.env, tktid)
        req = self._post_req('needinfo', ticket)
        self.assertTrue(self.tktmod.match_request(req))
        self.assertRaises(RequestDone, self.tktmod.process_request, req)
        ticket = Ticket(self.env, tktid)
        self.assertEqual('john', ticket['owner'])
        self.assertEqual('needinfo', ticket['status'])

    def test_set_owner_to_component_owner(self):
        self.env.config.set('ticket', 'workflow',
            'ConfigurableTicketWorkflow,TicketWorkflowOpOwnerComponent')
        self._config_set('ticket-workflow', [
            ('to-c-owner', '* -> assigned'),
            ('to-c-owner.operations', 'set_owner_to_component_owner'),
        ])
        self._insert_component('component3', 'foo')
        tktid = self._insert_ticket(summary='set owner to component owner',
                                    reporter='anonymous', owner='joe',
                                    component='component3')
        ticket = Ticket(self.env, tktid)
        req = self._post_req('to-c-owner', ticket)
        self.assertTrue(self.tktmod.match_request(req))
        self.assertRaises(RequestDone, self.tktmod.process_request, req)
        ticket = Ticket(self.env, tktid)
        self.assertEqual('foo', ticket['owner'])
        self.assertEqual('assigned', ticket['status'])

    def test_set_owner_to_component_owner_with_missing_component(self):
        self.env.config.set('ticket', 'workflow',
            'ConfigurableTicketWorkflow,TicketWorkflowOpOwnerComponent')
        self._config_set('ticket-workflow', [
            ('to-c-owner', '* -> assigned'),
            ('to-c-owner.operations', 'set_owner_to_component_owner'),
        ])
        tktid = self._insert_ticket(summary='set owner to component owner',
                                    reporter='anonymous', owner='joe',
                                    component='component3')
        ticket = Ticket(self.env, tktid)
        req = self._post_req('to-c-owner', ticket)
        self.assertTrue(self.tktmod.match_request(req))
        self.assertRaises(RequestDone, self.tktmod.process_request, req)
        ticket = Ticket(self.env, tktid)
        self.assertEqual('', ticket['owner'])
        self.assertEqual('assigned', ticket['status'])

    def test_set_owner_to_field(self):
        self.env.config.set('ticket', 'workflow',
            'ConfigurableTicketWorkflow,TicketWorkflowOpOwnerField')
        self._config_set('ticket-workflow', [
            ('to-owner', '* -> assigned'),
            ('to-owner.operations', 'set_owner_to_field'),
            ('to-owner.set_owner_to_field', 'keywords'),
        ])
        tktid = self._insert_ticket(summary='set owner to field',
                                    reporter='anonymous', owner='joe',
                                    keywords='john')
        ticket = Ticket(self.env, tktid)
        req = self._post_req('to-owner', ticket)
        self.assertTrue(self.tktmod.match_request(req))
        self.assertRaises(RequestDone, self.tktmod.process_request, req)
        ticket = Ticket(self.env, tktid)
        self.assertEqual('john', ticket['owner'])
        self.assertEqual('assigned', ticket['status'])

    def test_set_owner_to_previous(self):
        self.env.config.set('ticket', 'workflow',
            'ConfigurableTicketWorkflow,TicketWorkflowOpOwnerPrevious')
        self._config_set('ticket-workflow', [
            ('to-prev', '* -> assigned'),
            ('to-prev.operations', 'set_owner_to_previous'),
        ])
        tktid = self._insert_ticket(when=datetime(2017, 3, 9, tzinfo=utc),
                                    summary='set owner to previous',
                                    reporter='anonymous', owner='joe')

        ticket = Ticket(self.env, tktid)
        req = self._post_req('to-prev', ticket)
        self.assertTrue(self.tktmod.match_request(req))
        self.assertRaises(RequestDone, self.tktmod.process_request, req)
        ticket = Ticket(self.env, tktid)
        self.assertEqual('joe', ticket['owner'])
        self.assertEqual('assigned', ticket['status'])

        ticket = Ticket(self.env, tktid)
        ticket['owner'] = 'alice'
        ticket.save_changes(when=datetime(2017, 3, 9, 1, tzinfo=utc))
        ticket['owner'] = 'john'
        ticket.save_changes(when=datetime(2017, 3, 9, 2, tzinfo=utc))

        ticket = Ticket(self.env, tktid)
        req = self._post_req('to-prev', ticket)
        self.assertTrue(self.tktmod.match_request(req))
        self.assertRaises(RequestDone, self.tktmod.process_request, req)
        ticket = Ticket(self.env, tktid)
        self.assertEqual('alice', ticket['owner'])
        self.assertEqual('assigned', ticket['status'])

        ticket = Ticket(self.env, tktid)
        req = self._post_req('to-prev', ticket)
        self.assertTrue(self.tktmod.match_request(req))
        self.assertRaises(RequestDone, self.tktmod.process_request, req)
        ticket = Ticket(self.env, tktid)
        self.assertEqual('john', ticket['owner'])
        self.assertEqual('assigned', ticket['status'])

    def test_set_status_to_previous(self):
        self.env.config.set('ticket', 'workflow',
            'ConfigurableTicketWorkflow,TicketWorkflowOpStatusPrevious')
        self._config_set('ticket-workflow', [
            ('revert-status', '* -> *'),
            ('revert-status.operations', 'set_status_to_previous'),
        ])
        tktid = self._insert_ticket(when=datetime(2017, 3, 9, tzinfo=utc),
                                    summary='set status to previous',
                                    reporter='anonymous', owner='joe')

        ticket = Ticket(self.env, tktid)
        req = self._post_req('revert-status', ticket)
        self.assertTrue(self.tktmod.match_request(req))
        self.assertRaises(RequestDone, self.tktmod.process_request, req)
        ticket = Ticket(self.env, tktid)
        self.assertEqual('new', ticket['status'])

        ticket = Ticket(self.env, tktid)
        ticket['status'] = 'assigned'
        ticket.save_changes(when=datetime(2017, 3, 9, 1, tzinfo=utc))
        ticket['status'] = 'closed'
        ticket.save_changes(when=datetime(2017, 3, 9, 2, tzinfo=utc))

        ticket = Ticket(self.env, tktid)
        req = self._post_req('revert-status', ticket)
        self.assertTrue(self.tktmod.match_request(req))
        self.assertRaises(RequestDone, self.tktmod.process_request, req)
        ticket = Ticket(self.env, tktid)
        self.assertEqual('assigned', ticket['status'])

    def test_reset_milestone(self):
        self.env.config.set('ticket', 'workflow',
            'ConfigurableTicketWorkflow,TicketWorkflowOpResetMilestone')
        self._config_set('ticket-workflow', [
            ('reset-milestone', '* -> *'),
            ('reset-milestone.operations', 'reset_milestone'),
        ])
        tktid = self._insert_ticket(when=datetime(2017, 3, 9, tzinfo=utc),
                                    summary='reset milestone',
                                    milestone='milestone1',
                                    reporter='anonymous', owner='joe')

        ticket = Ticket(self.env, tktid)
        req = self._post_req('reset-milestone', ticket)
        self.assertTrue(self.tktmod.match_request(req))
        self.assertRaises(RequestDone, self.tktmod.process_request, req)
        ticket = Ticket(self.env, tktid)
        self.assertEqual('milestone1', ticket['milestone'])

        milestone = Milestone(self.env, ticket['milestone'])
        milestone.completed = datetime(2017, 3, 8, tzinfo=utc)
        milestone.update()
        req = self._post_req('reset-milestone', ticket)
        self.assertTrue(self.tktmod.match_request(req))
        self.assertRaises(RequestDone, self.tktmod.process_request, req)
        ticket = Ticket(self.env, tktid)
        self.assertEqual('', ticket['milestone'])

        ticket['milestone'] = 'unknown-milestone'
        ticket.save_changes(when=datetime(2017, 3, 8, 1, tzinfo=utc))
        req = self._post_req('reset-milestone', ticket)
        self.assertTrue(self.tktmod.match_request(req))
        self.assertRaises(RequestDone, self.tktmod.process_request, req)
        ticket = Ticket(self.env, tktid)
        self.assertEqual('unknown-milestone', ticket['milestone'])


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(AdvancedTicketWorkflowTestCase))
    return suite
