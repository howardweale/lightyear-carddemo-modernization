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
