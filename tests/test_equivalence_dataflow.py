import copy
import unittest
from lightyear_mainframe.equivalence_automation import sealed
from lightyear_mainframe.equivalence_dataflow import dead_store, recheck_dead_store, output_relevance


def span(start=0, length=2): return dict(area='WS', offset=start, length=length)


def node(name, reads=(), writes=(), successors=(), observable=False, branch=False):
    return dict(id=name, reads=list(reads), writes=list(writes), successors=list(successors),
                observable=observable, branch=branch, effect_order='reads-before-writes')


def cfg(*nodes): return sealed(dict(complete=True, unsupported=[], nodes=list(nodes)))


class DataflowTests(unittest.TestCase):
    def test_overwrite_both_paths_and_recheck(self):
        g = cfg(node('branch', successors=['a', 'b'], branch=True),
                node('a', writes=[span()]), node('b', writes=[span()]))
        proof = dead_store(g, ['branch'], [span()])
        self.assertTrue(recheck_dead_store(g, proof))
        self.assertFalse(proof['resolution_authorized'])

    def test_alias_read_before_overwrite_blocks(self):
        g = cfg(node('a', reads=[span(1,1)], writes=[span()]))
        self.assertFalse(dead_store(g, ['a'], [span()])['overwritten_on_every_path'])

    def test_partial_overwrites_accumulate(self):
        g = cfg(node('a', writes=[span(0,1)], successors=['b']), node('b', writes=[span(1,1)]))
        self.assertTrue(dead_store(g, ['a'], [span()])['overwritten_on_every_path'])

    def test_early_exit_and_cycle_do_not_prove_dead_store(self):
        for end in (node('b'), node('b', successors=['a'])):
            g = cfg(node('a', writes=[span(0,1)], successors=['b']), end)
            self.assertFalse(dead_store(g, ['a'], [span()])['overwritten_on_every_path'])

    def test_incomplete_cfg_and_tampered_certificate_refused(self):
        g = cfg(node('a', writes=[span()]))
        proof = dead_store(g, ['a'], [span()]); proof['states'] = []
        with self.assertRaises(ValueError): recheck_dead_store(g, proof)
        bad = sealed(dict(complete=False, unsupported=['CALL'], nodes=g['nodes']))
        with self.assertRaises(ValueError): dead_store(bad, ['a'], [span()])

    def test_fixpoint_tracks_alias_bytes_and_branch_sinks(self):
        g = cfg(node('a', reads=[span(0,1)], writes=[span(1,1)]),
                node('b', reads=[span(1,1)], writes=[span(2,1)]),
                node('c', reads=[span(2,1)], branch=True))
        result = output_relevance(g)
        self.assertEqual([['WS',0], ['WS',1], ['WS',2]], result['relevant_bytes'])
        self.assertFalse(result['resolution_authorized'])


if __name__ == '__main__': unittest.main()

class AreaKindLimitsTests(unittest.TestCase):
    def test_large_working_storage_and_bounded_fd(self):
        from lightyear_mainframe.equivalence_dataflow import cells
        large=span(length=171156)
        self.assertEqual(171156,len(cells([large],area_kinds={'WS':'WORKING-STORAGE'})))
        with self.assertRaisesRegex(ValueError,'invalid-byte-span'):cells([large],area_kinds={'WS':'FD'})
        with self.assertRaisesRegex(ValueError,'invalid-byte-span'):cells([span(32759,2)],area_kinds={'WS':'FD'})
        with self.assertRaisesRegex(ValueError,'unbound-byte-area-kind'):cells([span()],area_kinds={})
        graph=sealed(dict(complete=True,unsupported=[],area_kinds={'WS':'WORKING-STORAGE'},nodes=[node('overwrite',writes=[large])]))
        certificate=dead_store(graph,['overwrite'],[large])
        self.assertTrue(recheck_dead_store(graph,certificate))
        changed=sealed(dict(graph,area_kinds={'WS':'FD'}))
        with self.assertRaises(ValueError):recheck_dead_store(changed,certificate)


class ProductionAreaKindTests(unittest.TestCase):
    def make_cfg(self, nodes, kinds=None):
        return sealed(dict(complete=True, unsupported=[], nodes=nodes,
                           area_kinds=kinds if kinds is not None else {'WS': 'WORKING-STORAGE'}))

    def test_large_offsets_flow_through_graph_dead_store_and_recheck(self):
        # A small interval beyond the FD ceiling exercises the WS limit without
        # allocating a large certificate. Reads, writes and changed spans matter.
        from lightyear_mainframe.equivalence_dataflow import graph
        high = span(171154, 2)
        g = self.make_cfg([node('first', writes=[span(171154, 1)], successors=['last']),
                           node('last', writes=[span(171155, 1)])])
        self.assertEqual({'first', 'last'}, set(graph(g)))
        proof = dead_store(g, ['first'], [high])
        self.assertTrue(proof['overwritten_on_every_path'])
        self.assertTrue(recheck_dead_store(g, proof))
        self.assertFalse(proof['resolution_authorized'])
        blocked = self.make_cfg([node('alias', reads=[span(171155, 1)], writes=[high])])
        self.assertFalse(dead_store(blocked, ['alias'], [high])['overwritten_on_every_path'])

    def test_large_offsets_flow_through_output_sinks_and_dependency_fixpoint(self):
        for sink in ('observable', 'branch'):
            with self.subTest(sink=sink):
                g = self.make_cfg([
                    node('producer', reads=[span(171154, 1)], writes=[span(171155, 1)]),
                    node('sink', reads=[span(171155, 1)], **{sink: True})])
                proof = output_relevance(g)
                self.assertEqual([['WS', 171154], ['WS', 171155]], proof['relevant_bytes'])
                self.assertFalse(proof['resolution_authorized'])

    def test_production_entrypoints_refuse_fd_and_missing_area_bindings(self):
        from lightyear_mainframe.equivalence_dataflow import graph
        high = span(171155, 1)
        for kinds in ({'WS': 'FD'}, {}, {'WS': 'UNKNOWN'}):
            for consumer in (graph, output_relevance,
                             lambda g: dead_store(g, ['n'], [high])):
                with self.subTest(kinds=kinds, consumer=consumer):
                    g = self.make_cfg([node('n', reads=[high], writes=[high], observable=True)], kinds)
                    with self.assertRaises(ValueError):
                        consumer(g)

    def test_each_production_cell_conversion_receives_the_explicit_kind_map(self):
        # This sentinel rejects an omitted keyword even when a low-offset
        # fixture would accidentally fit the backward-compatible FD default.
        from unittest.mock import patch
        from lightyear_mainframe import equivalence_dataflow as dataflow
        original = dataflow.cells
        kinds = {'WS': 'WORKING-STORAGE'}
        g = self.make_cfg([node('n', reads=[span(4, 1)], writes=[span()], observable=True)], kinds)
        def require_bound(spans, *, area_kinds):
            self.assertIs(kinds, area_kinds)
            return original(spans, area_kinds=area_kinds)
        with patch.object(dataflow, 'cells', side_effect=require_bound) as calls:
            dataflow.graph(g)
            proof = dead_store(g, ['n'], [span()])
            self.assertTrue(recheck_dead_store(g, proof))
            self.assertEqual([['WS', 4]], output_relevance(g)['relevant_bytes'])
            self.assertGreater(calls.call_count, 0)
