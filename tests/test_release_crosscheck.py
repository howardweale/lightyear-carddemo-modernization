import copy
import unittest
from tools.crosscheck_release_threshold import check


class CrosscheckTests(unittest.TestCase):
    def test_independent_denominator_rejects_inflated_tower_count(self):
        executed = dict(status='executed')
        fresh = [dict(id='kill',status='killed-failure',baseline=executed,actual=executed),
                 dict(id='proof',status='survived'),dict(id='gap',status='evidence-gap'),dict(id='compile',status='not-compiled')]
        reviews = [dict(id='proof', TCE={'identical':True})]
        tower = dict(sites=4,killed=1,eligible=2,kill_rate='1/2',minimum_50_met=False,at_least_90_percent=False,
            compiler_refusals=['compile'],excluded_equivalents=[{'id':'proof'}],unresolved_survivors=[{'id':'gap'}])
        self.assertTrue(check(fresh,reviews,[],'twin',tower)['passed'])
        changed = copy.deepcopy(tower);changed['eligible']=1;changed['kill_rate']='1/1'
        with self.assertRaises(ValueError):check(fresh,reviews,[],'twin',changed)
        with self.assertRaises(ValueError):check(fresh,reviews,[],'zos-facing',tower)


if __name__ == '__main__':unittest.main()
