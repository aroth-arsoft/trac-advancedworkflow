# -*- coding: utf-8 -*-
#
# Copyright (C) 2008-2014 Eli Carter <elicarter@retracile.net>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution.

"""Trac plugin that provides a number of advanced operations for customizable
workflows.
"""

import os
from datetime import datetime
from pkg_resources import resource_filename
from subprocess import call

from trac.core import implements, Component
from trac.notification.api import NotificationSystem
from trac.ticket import model
from trac.ticket.api import ITicketActionController, TicketSystem
from trac.ticket.default_workflow import ConfigurableTicketWorkflow
from trac.ticket.notification import TicketChangeEvent
from trac.resource import ResourceNotFound
from trac.util.datefmt import utc
from trac.util.html import html
from trac.util.text import to_unicode
from trac.util.translation import domain_functions
from trac.web.chrome import Chrome, add_warning


_, tag_, add_domain = domain_functions('advancedworkflow',
                                       '_', 'tag_', 'add_domain')


class TicketWorkflowOpBase(Component):
    """Abstract base class for 'simple' ticket workflow operations."""

    implements(ITicketActionController)
    abstract = True

    _op_name = None  # Must be specified.

    def __init__(self):
        try:
            locale_dir = resource_filename(__name__, 'locale')
        except:
            pass
        else:
            add_domain(self.env.path, locale_dir)

    def get_configurable_workflow(self):
        controllers = TicketSystem(self.env).action_controllers
        for controller in controllers:
            if isinstance(controller, ConfigurableTicketWorkflow):
                return controller
        return ConfigurableTicketWorkflow(self.env)

    # ITicketActionController methods

    def get_ticket_actions(self, req, ticket):
        """Finds the actions that use this operation"""
        controller = self.get_configurable_workflow()
        return controller.get_actions_by_operation_for_req(req, ticket,
                                                           self._op_name)

    def get_all_status(self):
        """Provide any additional status values"""
        # We don't have anything special here; the statuses will be
        # recognized by the default controller.
        return []

    # This should most likely be overridden to be more functional
    def render_ticket_action_control(self, req, ticket, action):
        """Returns the action control"""
        actions = self.get_configurable_workflow().actions
        label = actions[action]['label']
        return label, '', ''

    def get_ticket_changes(self, req, ticket, action):
        """Must be implemented in subclasses"""
        raise NotImplementedError

    def apply_action_side_effects(self, req, ticket, action):
        """No side effects"""
        pass

    # Internal methods

    def _get_hint_to_change_owner(self, req, ticket, new_owner):
        if new_owner:
            return _("The owner will be changed from %(current_owner)s to "
                     "%(selected_owner)s.",
                     current_owner=self._format_author(req, ticket['owner']),
                     selected_owner=self._format_author(req, new_owner))
        else:
            return _("The owner will be deleted.")

    def _get_hint_to_change_state(self, req, ticket, status):
        if ticket['status'] is None:
            return _("The status will be '%(name)s'", name=status)
        else:
            return _("Next status will be '%(name)s'", name=status)

    def _format_author(self, req, author):
        return Chrome(self.env).format_author(req, author)


class TicketWorkflowOpOwnerReporter(TicketWorkflowOpBase):
    """Sets the owner to the reporter of the ticket.

    needinfo = * -> needinfo
    needinfo.name = Need info
    needinfo.operations = set_owner_to_reporter


    Don't forget to add the `TicketWorkflowOpOwnerReporter` to the workflow
    option in [ticket].
    If there is no workflow option, the line will look like this:

    workflow = ConfigurableTicketWorkflow,TicketWorkflowOpOwnerReporter
    """

    _op_name = 'set_owner_to_reporter'

    # ITicketActionController methods

    def render_ticket_action_control(self, req, ticket, action):
        """Returns the action control"""
        actions = self.get_configurable_workflow().actions
        label = actions[action]['label']
        hint = self._get_hint_to_change_owner(req, ticket, ticket['reporter'])
        return label, '', hint

    def get_ticket_changes(self, req, ticket, action):
        """Returns the change of owner."""
        return {'owner': ticket['reporter']}


class TicketWorkflowOpOwnerComponent(TicketWorkflowOpBase):
    """Sets the owner to the default owner for the component.

    <someaction>.operations = set_owner_to_component_owner

    Don't forget to add the `TicketWorkflowOpOwnerComponent` to the workflow
    option in [ticket].
    If there is no workflow option, the line will look like this:

    workflow = ConfigurableTicketWorkflow,TicketWorkflowOpOwnerComponent
    """

    _op_name = 'set_owner_to_component_owner'

    # ITicketActionController methods

    def render_ticket_action_control(self, req, ticket, action):
        """Returns the action control"""
        actions = self.get_configurable_workflow().actions
        label = actions[action]['label']
        hint = self._get_hint_to_change_owner(req, ticket,
                                              self._new_owner(ticket))
        return label, '', hint

    def get_ticket_changes(self, req, ticket, action):
        """Returns the change of owner."""
        return {'owner': self._new_owner(ticket)}

    def _new_owner(self, ticket):
        """Determines the new owner"""
        try:
            component = model.Component(self.env, name=ticket['component'])
            return component.owner
        except ResourceNotFound, e:
            self.log.warning("In %s, %s", self._op_name, to_unicode(e))
            return None


class TicketWorkflowOpOwnerField(TicketWorkflowOpBase):
    """Sets the owner to the value of a ticket field

    <someaction>.operations = set_owner_to_field
    <someaction>.set_owner_to_field = myfield

    Don't forget to add the `TicketWorkflowOpOwnerField` to the workflow
    option in [ticket].
    If there is no workflow option, the line will look like this:

    workflow = ConfigurableTicketWorkflow,TicketWorkflowOpOwnerField
    """

    _op_name = 'set_owner_to_field'

    # ITicketActionController methods

    def render_ticket_action_control(self, req, ticket, action):
        """Returns the action control"""
        actions = self.get_configurable_workflow().actions
        label = actions[action]['label']
        new_owner = self._new_owner(action, ticket)
        hint = self._get_hint_to_change_owner(req, ticket, new_owner)
        return label, '', hint

    def get_ticket_changes(self, req, ticket, action):
        """Returns the change of owner."""
        return {'owner': self._new_owner(action, ticket)}

    def _new_owner(self, action, ticket):
        """Determines the new owner"""
        # Should probably do some sanity checking...
        field = self.config.get('ticket-workflow',
                                action + '.' + self._op_name).strip()
        return ticket[field]


class TicketWorkflowOpFieldAuthor(TicketWorkflowOpBase):
    """Sets the value of a ticket field to the current user

    <someaction>.operations = set_field_to_author
    <someaction>.set_field_to_author = myfield

    Don't forget to add the `TicketWorkflowOpFieldAuthor` to the workflow
    option in [ticket].
    If there is no workflow option, the line will look like this:

    workflow = ConfigurableTicketWorkflow,TicketWorkflowOpFieldAuthor
    """

    _op_name = 'set_field_to_author'

    # ITicketActionController methods

    def render_ticket_action_control(self, req, ticket, action):
        """Returns the action control"""
        actions = ConfigurableTicketWorkflow(self.env).actions
        label = actions[action]['label']
        hint = _("The '%(field)s' field will be set to '%(username)s'.",
            field=self._field_name(action, ticket),
            username=req.authname)
        control = html('')
        return (label, control, hint)

    def get_ticket_changes(self, req, ticket, action):
        """Returns the change of the field."""
        return {self._field_name(action, ticket): req.authname}

    def _field_name(self, action, ticket):
        """Determines the field to set to self """
        field = self.config.get('ticket-workflow',
                                action + '.' + self._op_name).strip()
        return field


class TicketWorkflowOpFieldsClear(TicketWorkflowOpBase):
    """Clears the value of the ticket field(s)

    <someaction>.operations = clear_fields
    <someaction>.clear_fields = myfield_one, myfield_two

    Don't forget to add the `TicketWorkflowOpFieldsClear` to the workflow
    option in [ticket].
    If there is no workflow option, the line will look like this:

    workflow = ConfigurableTicketWorkflow,TicketWorkflowOpFieldsClear
    """

    _op_name = 'clear_fields'

    # ITicketActionController methods

    def render_ticket_action_control(self, req, ticket, action):
        """Returns the action control"""
        actions = ConfigurableTicketWorkflow(self.env).actions
        label = actions[action]['label']
        fields = ["'%s'" % x for x in self._field_names(action, ticket)]
        hint = ngettext("The %(fields)s field will be cleared.",
                        "The %(fields)s fields will be cleared.", len(fields),
                        fields=', '.join(fields))
        control = html('')
        return (label, control, hint)

    def get_ticket_changes(self, req, ticket, action):
        """Returns the changes to the fields."""
        return {x: '' for x in self._field_names(action, ticket)}

    def _field_names(self, action, ticket):
        """Determines the fields to set to blank """
        return self.config.getlist('ticket-workflow',
                                   action + '.' + self._op_name)


class TicketWorkflowOpOwnerPrevious(TicketWorkflowOpBase):
    """Sets the owner to the previous owner

    Don't forget to add the `TicketWorkflowOpOwnerPrevious` to the workflow
    option in [ticket].
    If there is no workflow option, the line will look like this:

    workflow = ConfigurableTicketWorkflow,TicketWorkflowOpOwnerPrevious
    """

    _op_name = 'set_owner_to_previous'

    # ITicketActionController methods

    def render_ticket_action_control(self, req, ticket, action):
        """Returns the action control"""
        actions = self.get_configurable_workflow().actions
        label = actions[action]['label']
        new_owner = self._new_owner(ticket)
        hint = self._get_hint_to_change_owner(req, ticket, new_owner)
        return label, '', hint

    def get_ticket_changes(self, req, ticket, action):
        """Returns the change of owner."""
        return {'owner': self._new_owner(ticket)}

    def _new_owner(self, ticket):
        """Determines the new owner"""
        rows = self.env.db_query("""
            SELECT oldvalue FROM ticket_change WHERE ticket=%s
            AND field='owner' ORDER BY time DESC LIMIT 1
            """, (ticket.id, ))
        return rows[0][0] if rows else ticket['owner']


class TicketWorkflowOpStatusPrevious(TicketWorkflowOpBase):
    """Sets the status to the previous status

    Don't forget to add the `TicketWorkflowOpStatusPrevious` to the workflow
    option in [ticket].
    If there is no workflow option, the line will look like this:

    workflow = ConfigurableTicketWorkflow,TicketWorkflowOpStatusPrevious
    """

    _op_name = 'set_status_to_previous'

    # ITicketActionController methods

    def render_ticket_action_control(self, req, ticket, action):
        """Returns the action control"""
        actions = self.get_configurable_workflow().actions
        label = actions[action]['label']
        new_status = self._new_status(ticket)
        if new_status != self._old_status(ticket):
            hint = _("The status will be changed to %(status)s.",
                     status=new_status)
        else:
            hint = ''
        return label, '', hint

    def get_ticket_changes(self, req, ticket, action):
        """Returns the change of status."""
        return {'status': self._new_status(ticket)}

    def _old_status(self, ticket):
        """Determines what the ticket state was (is)"""
        return ticket._old.get('status', ticket['status'])

    def _new_status(self, ticket):
        """Determines the new status"""
        rows = self.env.db_query("""
            SELECT oldvalue FROM ticket_change WHERE ticket=%s
            AND field='status' ORDER BY time DESC LIMIT 1
          """, (ticket.id, ))
        return rows[0][0] if rows else 'new'


class TicketWorkflowOpRunExternal(TicketWorkflowOpBase):
    """Action to allow running an external command as a side-effect.

    If it is a lengthy task, it should daemonize so the webserver can get back
    to doing its thing.  If the script exits with a non-zero return code, an
    error will be logged to the Trac log.
    The plugin will look for a script named <tracenv>/hooks/<someaction>, and
    will pass it 2 parameters: the ticket number, and the user.

    <someaction>.operations = run_external
    <someaction>.run_external = Hint for the user

    Don't forget to add the `TicketWorkflowOpRunExternal` to the workflow
    option in [ticket].
    If there is no workflow option, the line will look like this:

    workflow = ConfigurableTicketWorkflow,TicketWorkflowOpRunExternal
    """

    implements(ITicketActionController)

    # ITicketActionController methods

    def get_ticket_actions(self, req, ticket):
        """Finds the actions that use this operation"""
        controller = self.get_configurable_workflow()
        return controller.get_actions_by_operation_for_req(req, ticket,
                                                           'run_external')

    def get_all_status(self):
        """Provide any additional status values"""
        # We don't have anything special here; the statuses will be recognized
        # by the default controller.
        return []

    def render_ticket_action_control(self, req, ticket, action):
        """Returns the action control"""
        actions = self.get_configurable_workflow().actions
        label = actions[action]['label']
        hint = self.config.get('ticket-workflow',
                               action + '.run_external').strip()
        if not hint:
            hint = _("Will run external script.")
        return label, '', hint

    def get_ticket_changes(self, req, ticket, action):
        """No changes to the ticket"""
        return {}

    def apply_action_side_effects(self, req, ticket, action):
        """Run the external script"""
        print "running external script for %s" % action
        script = os.path.join(self.env.path, 'hooks', action)
        for extension in ('', '.exe', '.cmd', '.bat'):
            if os.path.exists(script + extension):
                script += extension
                break
        else:
            self.env.log.error("Error in ticket workflow config; could not "
                               "find external command to run for %s in %s",
                               action, os.path.join(self.env.path, 'hooks'))
            return
        retval = call([script, str(ticket.id), req.authname])
        if retval:
            self.env.log.error("External script %r exited with return code "
                               "%s.", script, retval)


class TicketWorkflowOpTriage(TicketWorkflowOpBase):
    """Action to split a workflow based on a field

    <someaction> = somestatus -> *
    <someaction>.operations = triage
    <someaction>.triage_field = type
    <someaction>.triage_split = defect -> new_defect, task -> new_task, enhancement -> new_enhancement

    Don't forget to add the `TicketWorkflowOpTriage` to the workflow option in
    [ticket].
    If using the default workflow, the line will look like this:

    workflow = ConfigurableTicketWorkflow,TicketWorkflowOpTriage
    """

    _op_name = 'triage'

    # ITicketActionController methods

    def render_ticket_action_control(self, req, ticket, action):
        """Returns the action control"""
        actions = self.get_configurable_workflow().actions
        label = actions[action]['label']
        new_status = self._new_status(ticket, action)
        if not ticket.exists:
            hint = _("The status will be '%(name)s'.", name=new_status)
        elif new_status != ticket['status']:
            hint = _("Next status will be '%(name)s'.", name=new_status)
        else:
            hint = ''
        return label, '', hint

    def get_ticket_changes(self, req, ticket, action):
        """Returns the change of status."""
        return {'status': self._new_status(ticket, action)}

    def _new_status(self, ticket, action):
        """Determines the new status"""
        field = self.config.get('ticket-workflow',
                                action + '.triage_field').strip()
        transitions = self.config.get('ticket-workflow',
                                      action + '.triage_split').strip()
        for transition in [x.strip() for x in transitions.split(',')]:
            value, status = [y.strip() for y in transition.split('->')]
            if value == ticket[field].strip():
                break
        else:
            self.env.log.error("Bad configuration for 'triage' operation in "
                               "action '%s'", action)
            status = 'new'
        return status


class TicketWorkflowOpXRef(TicketWorkflowOpBase):
    """Adds a cross reference to another ticket

    <someaction>.operations = xref
    <someaction>.xref = "Ticket %s is related to this ticket"
    <someaction>.xref_local = "Ticket %s was marked as related to this ticket"
    <someaction>.xref_hint = "The specified ticket will be cross-referenced with this ticket"

    The example values shown are the default values.
    Don't forget to add the `TicketWorkflowOpXRef` to the workflow
    option in [ticket].
    If there is no workflow option, the line will look like this:

    workflow = ConfigurableTicketWorkflow,TicketWorkflowOpXRef
    """

    _op_name = 'xref'

    # ITicketActionController methods

    def render_ticket_action_control(self, req, ticket, action):
        """Returns the action control"""
        id = 'action_%s_xref' % action
        ticketnum = req.args.get(id, '')
        actions = self.get_configurable_workflow().actions
        label = actions[action]['label']
        hint = actions[action].get('xref_hint') or \
               _("The specified ticket will be cross-referenced with this "
                 "ticket.")
        control = html.input(type='text', id=id, name=id, value=ticketnum)
        return label, control, hint

    def get_ticket_changes(self, req, ticket, action):
        # WARNING: Directly modifying the ticket in this method breaks the
        # intent of this method.  But it does accomplish the desired goal.
        if not 'preview' in req.args:
            id = 'action_%s_xref' % action
            ticket_num = req.args.get(id).strip('#')

            try:
                model.Ticket(self.env, ticket_num)
            except ValueError:
                req.args['preview'] = True
                add_warning(req, 'The cross-referenced ticket number "%s" '
                                 'was not a number', ticket_num)
                return {}
            except ResourceNotFound, e:
                #put in preview mode to prevent ticket being saved
                req.args['preview'] = True
                add_warning(req, "Unable to cross-reference Ticket #%s (%s).",
                            ticket_num, e.message)
                return {}

            oldcomment = req.args.get('comment')
            actions = self.get_configurable_workflow().actions
            format_string = actions[action].get('xref_local',
                                                "Ticket %s was marked as "
                                                "related to this ticket")
            # Add a comment to this ticket to indicate that the "remote"
            # ticket is related to it.  (But only if <action>.xref_local
            # was set in the config.)
            if format_string:
                comment = format_string % ('#%s' % ticket_num)
                req.args['comment'] = "%s%s%s" % \
                    (comment, oldcomment and "[[BR]]" or "", oldcomment or "")

        """Returns no changes."""
        return {}

    def apply_action_side_effects(self, req, ticket, action):
        """Add a cross-reference comment to the other ticket"""
        # TODO: This needs a lot more error checking.
        id = 'action_%s_xref' % action
        ticketnum = req.args.get(id).strip('#')
        actions = self.get_configurable_workflow().actions
        author = req.authname

        # Add a comment to the "remote" ticket to indicate this ticket is
        # related to it.
        format_string = actions[action].get('xref', "Ticket %s is related "
                                                    "to this ticket")
        comment = format_string % ('#%s' % ticket.id)
        # FIXME: we need a cnum to avoid messing up
        xticket = model.Ticket(self.env, ticketnum)
        # FIXME: We _assume_ we have sufficient permissions to comment on the
        # other ticket.
        now = datetime.now(utc)
        xticket.save_changes(author, comment, now)

        # Send notification on the other ticket
        event = TicketChangeEvent('changed', xticket, now, author)
        try:
            NotificationSystem(self.env).notify(event)
        except Exception, e:
            self.log.exception("Failure sending notification on change to "
                               "ticket #%s: %s", ticketnum, e)


class TicketWorkflowOpResetMilestone(TicketWorkflowOpBase):
    """Resets the ticket milestone if it is assigned to a completed milestone.
    This is useful for reopen operations.

    reopened = closed -> reopened
    reopened.name = Reopened
    reopened.operations = reset_milestone


    Don't forget to add the `TicketWorkflowOpResetMilestone` to the  workflow
    option in [ticket].
    If there is no workflow option, the line will look like this:

    workflow =  ConfigurableTicketWorkflow,TicketWorkflowOpResetMilestone
    """

    _op_name = 'reset_milestone'

    # ITicketActionController methods

    def render_ticket_action_control(self, req, ticket, action):
        """Returns the action control"""
        actions = self.get_configurable_workflow().actions
        label = actions[action]['label']
        # check if the assigned milestone has been completed
        milestone = self._fetch_milestone(ticket)
        if milestone and milestone.is_completed:
            hint = _("The milestone will be reset.")
        else:
            hint = ''
        return label, '', hint

    def get_ticket_changes(self, req, ticket, action):
        """Returns the change of milestone, if needed."""
        milestone = self._fetch_milestone(ticket)
        if milestone and milestone.is_completed:
            return {'milestone': ''}
        return {}

    def _fetch_milestone(self, ticket):
        if ticket['milestone']:
            try:
                return model.Milestone(self.env, ticket['milestone'])
            except ResourceNotFound, e:
                self.log.warning("In %s, %s", self._op_name, to_unicode(e))
        return None


class TicketWorkflowOpSetState(TicketWorkflowOpBase):
    """Sets the state of the ticket when executing another operation.

    Don't forget to add the `TicketWorkflowOpSetState` to the workflow
    option in [ticket].
    If there is no workflow option, the line will look like this:

    workflow = ConfigurableTicketWorkflow,TicketWorkflowOpSetState
    """

    _op_name = 'set_state'

    # ITicketActionController methods

    def render_ticket_action_control(self, req, ticket, action):
        """Returns the action control"""
        actions = self.get_configurable_workflow().actions
        label = actions[action]['name']
        newstate = actions[action]['newstate']
        if newstate == ticket['status']:
            hint = ''
        else:
            hint = self._get_hint_to_change_state(req, ticket, newstate)
        return label, '', hint

    def get_ticket_changes(self, req, ticket, action):
        """Returns the change of owner."""
        actions = self.get_configurable_workflow().actions
        newstate = actions[action]['newstate']
        if newstate == ticket['status']:
            return {}
        else:
            return {'status': newstate}
