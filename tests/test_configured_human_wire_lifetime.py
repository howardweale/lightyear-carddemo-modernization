"""CI-only byte and callback relations, never genuine origin/admission evidence."""
import os
import unittest
from lightyear_factory.contracts import ContractError
from lightyear_factory.orchestrator import FactoryOrchestrator
from lightyear_factory.budgeted_providers import AccountedModelProvider
from lightyear_execution.configured_human_wire import bounded_response_bytes
from lightyear_execution.configured_human_terminal import _original_callback_bindings


def synthetic_callback_relation():
    # No constructor, runtime or origin registry is invoked. These unadmitted
    # objects exercise only callback identity equality; no callback is called.
    controller=object.__new__(FactoryOrchestrator)
    budget=object.__new__(AccountedModelProvider)
    for name,method in (('reservation_checkpoint','_reserve_model_call'),
                        ('observed_checkpoint','_checkpoint_accounting'),
                        ('transport_reservation_checkpoint','_reserve_model_transport'),
                        ('transport_observed_checkpoint','_observe_model_transport')):
        setattr(budget,name,getattr(controller,method))
    return controller,budget


class ConfiguredWireLifetimeTests(unittest.TestCase):
    def setUp(self):self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')

    def test_late_read_error_preserves_original_prefix(self):
        class Response:
            def __init__(self):self.count=0
            def read(self,n):
                self.count+=1
                if self.count==1:return b'original-partial-body'
                raise TimeoutError('synthetic')
        self.assertEqual(bounded_response_bytes(Response()),(b'original-partial-body',False))

    def test_initial_io_error_is_not_empty_success(self):
        class Response:
            def read(self,n):raise OSError('synthetic')
        self.assertEqual(bounded_response_bytes(Response()),(b'',False))

    def test_callback_relation_does_not_register_origin_or_run_callbacks(self):
        from lightyear_execution.configured_human_terminal import _ORIGINAL
        controller,budget=synthetic_callback_relation()
        self.assertEqual(len(_original_callback_bindings(controller,budget)),4)
        self.assertNotIn(controller,_ORIGINAL)

    def test_callback_from_another_controller_refused(self):
        controller,budget=synthetic_callback_relation()
        other,_=synthetic_callback_relation()
        budget.transport_reservation_checkpoint=other._reserve_model_transport
        with self.assertRaisesRegex(ContractError,'original-callback'):
            _original_callback_bindings(controller,budget)

    def test_wrapper_or_replaced_owner_method_refused(self):
        for change_owner in (False,True):
            controller,budget=synthetic_callback_relation()
            callback=lambda *args: None
            if change_owner:controller._reserve_model_call=callback
            budget.reservation_checkpoint=callback
            with self.assertRaisesRegex(ContractError,'original-callback'):
                _original_callback_bindings(controller,budget)

    def test_dictionary_cannot_supply_callback_owner(self):
        with self.assertRaisesRegex(ContractError,'native-callback-owner'):
            _original_callback_bindings({}, {})
