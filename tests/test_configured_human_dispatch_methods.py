"""CI-only native urllib method mutation refusals; no provider/admission/network."""
import os
import unittest
from urllib.request import build_opener
from lightyear_factory.additional_providers import _RecordedNoRedirect
from lightyear_factory.contracts import ContractError
from lightyear_execution.configured_human_recorded_transport import (
    _dispatch_fingerprint,_require_original_dispatch)


class OriginalDispatchMethods(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')
        self.director=build_opener(_RecordedNoRedirect())
        self.original=_dispatch_fingerprint(self.director)
        self.invoked=[]
    def replaced(self,*args,**kwargs):
        self.invoked.append(True)
        raise AssertionError('replacement must never be invoked')
    def refused(self):
        with self.assertRaisesRegex(ContractError,'dispatch-changed'):
            _require_original_dispatch(self.director,self.original)
        self.assertEqual(self.invoked,[])
    def test_original_methods_remain_stable_without_send(self):
        self.assertIsNone(_require_original_dispatch(self.director,self.original))
        self.assertEqual(self.invoked,[])
    def test_same_https_handler_replaced_open_is_refused(self):
        handler=self.director.handle_open['https'][0]
        handler.https_open=self.replaced
        self.refused()
    def test_same_request_processor_replacement_is_refused(self):
        handler=self.director.process_request['https'][0]
        handler.https_request=self.replaced
        self.refused()
    def test_same_response_processor_replacement_is_refused(self):
        handler=self.director.process_response['https'][0]
        handler.https_response=self.replaced
        self.refused()
    def test_same_error_handler_replacement_is_refused(self):
        handler=self.director.handle_error['http'][302][0]
        handler.http_error_302=self.replaced
        self.refused()
    def test_redirect_helper_replacement_is_refused(self):
        handler=next(h for h in self.director.handlers if type(h) is _RecordedNoRedirect)
        handler.redirect_request=self.replaced
        self.refused()
    def test_https_helper_replacement_is_refused(self):
        handler=self.director.handle_open['https'][0]
        handler.do_open=self.replaced
        self.refused()
    def test_director_chain_replacement_is_refused(self):
        self.director._call_chain=self.replaced
        self.refused()
    def test_handler_parent_replacement_is_refused(self):
        self.director.handle_open['https'][0].parent=object()
        self.refused()
    def test_missing_dispatch_callable_refuses_without_send(self):
        self.director.handle_open['https'][0].https_open=None
        with self.assertRaisesRegex(ContractError,'dispatch-method-shape'):
            _require_original_dispatch(self.director,self.original)
        self.assertEqual(self.invoked,[])
